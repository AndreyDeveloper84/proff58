"""Автообработка фото товара: контролёр качества и запись в `ProductImage`.

Здесь всё, что касается БД и storage; сама обработка байтов и признаков —
`image_processing`/`image_quality`. Разделяет три вещи, которые раньше жили в одном
поле `display`:

- **кандидат** (`candidate`) — свежий результат обработки, ждущий решения. Постановка
  в очередь, ошибка обработки и отклонение кандидата НИКОГДА не меняют витрину;
- **принятая копия** (`display`) — то, что реально показывает витрина
  (`ProductImage.storefront_image`), меняется только `_promote`/`accept_candidate`;
- **решение контролёра** (`qc_*`) — откуда взялся вердикт, какие признаки измерены,
  какая версия правил его вынесла.

Инварианты ADR-0014, которые держит этот модуль (доработка не отменяет ни один):

- исходный `image` и его `checksum` не трогаются никогда;
- файлы пишутся ДО транзакции (storage не откатывается), запись обновляется под
  `select_for_update` со сверкой имени оригинала и `revision` (растёт при каждом
  решении человека — старый воркер, читавший запись раньше, не перезапишет более
  новое решение);
- только `save(update_fields=...)`; удаление файлов — после коммита;
- `rejected` (закреплённый оригинал) и товары с `content_locked` не трогаются;
- прочий фон (`OTHER`) автоматика не обрабатывает — `SKIPPED` без кандидата, если
  только человек явно не запросил точечное удаление фона (`manual_rembg_requested`)
  для кадра, чьё назначение не promo/kit/in_use.

Идемпотентность: `candidate_render_key = sha256(источник + версия + маршрут +
модель rembg)`. Тот же ключ — тот же результат: повторная задача с тем же
исходником и параметрами не пишет файл заново и не зовёт нейросеть повторно.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.features import is_enabled

from . import image_processing, image_quality, image_rembg
from .image_archive import archive_candidate
from .models import (
    ImageMainFit,
    ImageProcessingMode,
    ImageProcessingStatus,
    ImagePurpose,
    ImageQcDecision,
    ImageQcSource,
    ImageReviewReason,
    ProductImage,
    ProductImageEvent,
    RejectedImageCandidate,
    product_image_display_path,
)

log = logging.getLogger(__name__)

FLAG = "product_image_autoprocess"
REMBG_MODEL = image_rembg.MODEL

#: Итоговые статусы: при текущей версии параметров и правил повторно не обрабатываем.
SETTLED = (
    ImageProcessingStatus.DONE,
    ImageProcessingStatus.NEEDS_REMBG,
    ImageProcessingStatus.NEEDS_REVIEW,
    ImageProcessingStatus.SKIPPED,
    ImageProcessingStatus.OBSERVED,
    ImageProcessingStatus.CANDIDATE_REJECTED,
)
#: Статусы, для которых `--status failed` вправе поставить задачу заново.
RETRYABLE = SETTLED + (ImageProcessingStatus.NONE, ImageProcessingStatus.FAILED)

_MAP_REASON_TO_LEGACY = {
    image_quality.Reason.EMPTY: ImageReviewReason.EMPTY,
    image_quality.Reason.SMALL: ImageReviewReason.SMALL,
    image_quality.Reason.TORN: ImageReviewReason.TORN,
    image_quality.Reason.DUPLICATE: ImageReviewReason.DUPLICATE,
}


class _Stale(Exception):
    """Запись удалили, фото заменили или решение уже принято, пока шла обработка."""


def enabled_routes() -> frozenset[str]:
    from django.conf import settings

    return frozenset(getattr(settings, "PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES", ()))


def rembg_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "PRODUCT_IMAGE_REMBG_ENABLED", True))


def _render_key(source_sha: str, mode: str) -> str:
    payload = f"{source_sha}:{image_processing.PROCESSING_VERSION}:{mode}:{REMBG_MODEL}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _log_event(
    image: ProductImage,
    *,
    kind: str,
    source: str,
    actor=None,
    render_key: str = "",
    checksum: str = "",
    before: dict | None = None,
    after: dict | None = None,
    reasons: list | None = None,
    note: str = "",
) -> None:
    ProductImageEvent.objects.create(
        image=image if image.pk else None,
        image_ref=image.pk,
        product_ref=image.product_id,
        kind=kind,
        source=source,
        actor=actor,
        render_key=render_key,
        checksum=checksum,
        before=before or {},
        after=after or {},
        reasons=reasons or [],
        note=note,
    )


# --- постановка в очередь ------------------------------------------------------


def schedule(image_id: int) -> None:
    """Поставить новое фото в очередь после коммита (сигнал сохранения).

    `robust=True`: упавший брокер не должен ронять сохранение фото в админке;
    `enqueue` в этом случае сам вернёт статус.
    """
    transaction.on_commit(lambda: enqueue(image_id), robust=True)


def enqueue(
    image_id: int,
    *,
    statuses: tuple[str, ...] = (ImageProcessingStatus.NONE,),
    outdated: bool = False,
    rembg: bool = False,
    force: bool = False,
) -> bool:
    """Пометить «в очереди» и отправить задачу. False — не подошёл статус или упал брокер.

    `outdated` добавляет готовые записи только со старой версией параметров ИЛИ
    правил контролёра — иначе запись, которую воркер успел обработать после
    выборки, ушла бы в очередь повторно. `rembg` — задача в очередь `rembg`
    (сервис `celery-rembg`). `force` — применение по ID (`process_product_images
    --manifest`) обходит глобальный флаг `product_image_autoprocess`, но не
    `content_locked` и не `rejected` — это решает уже `_process`.
    """
    from .tasks import process_product_image, remove_photo_background

    task = remove_photo_background if rembg else process_product_image

    match = Q(processing_status__in=statuses)
    if outdated:
        match |= Q(processing_status__in=SETTLED) & (
            Q(processing_version__lt=image_processing.PROCESSING_VERSION)
            | Q(qc_rules_version__lt=image_quality.QC_RULES_VERSION)
        )
    match &= ~Q(processing_status=ImageProcessingStatus.REJECTED)
    with transaction.atomic():
        previous = (
            ProductImage.objects.select_for_update()
            .filter(match, pk=image_id)
            .values_list("processing_status", flat=True)
            .first()
        )
        if previous is None:
            return False
        ProductImage.objects.filter(pk=image_id).update(
            processing_status=ImageProcessingStatus.QUEUED
        )
    try:
        task.delay(image_id, force=force)
    except Exception:
        log.exception("фото %s: задача не поставлена в очередь", image_id)
        ProductImage.objects.filter(
            pk=image_id, processing_status=ImageProcessingStatus.QUEUED
        ).update(processing_status=previous)
        return False
    return True


# --- обработка ---------------------------------------------------------------


def process_image(image_id: int, *, rembg: bool = False, force: bool = False) -> str:
    """Сделать кандидата и вынести решение контролёра. Возвращает итог обработки.

    `rembg=True` — задача сервиса нейросети: чёрный фон и подтверждённый вручную
    сложный фон обрабатываются удалением фона, а не откладываются. `force=True` —
    применение по ID обходит флаг `product_image_autoprocess` (не `content_locked`
    и не `rejected`).
    """
    try:
        return _process(image_id, rembg=rembg, force=force)
    except Exception:
        log.exception("фото %s: обработка упала", image_id)
        _mark_failed(image_id, error="internal_error")
        return ImageProcessingStatus.FAILED


def _process(image_id: int, *, rembg: bool = False, force: bool = False) -> str:
    release_to = ImageProcessingStatus.NEEDS_REMBG if rembg else ImageProcessingStatus.NONE
    image = ProductImage.objects.select_related("product").filter(pk=image_id).first()
    if image is None:
        return "missing"
    if not force and not is_enabled(FLAG):
        _release(image_id, to=release_to)
        return "disabled"
    if image.product.content_locked:
        _release(image_id, to=release_to)
        return "content_locked"
    if image.processing_status == ImageProcessingStatus.REJECTED:
        return "rejected"
    if (
        image.processing_status in SETTLED
        and image.processing_version >= image_processing.PROCESSING_VERSION
        and image.qc_rules_version >= image_quality.QC_RULES_VERSION
    ):
        return "up_to_date"
    if not image.image:
        _release(image_id, to=release_to)
        return "no_file"

    source_name = image.image.name
    revision = image.revision
    try:
        with image.image.storage.open(source_name, "rb") as fh:
            raw = fh.read()
        source_sha = hashlib.sha256(raw).hexdigest()
        result = image_processing.process(raw)
    except (OSError, image_processing.UnreadableImage) as exc:
        log.warning("фото %s не обработано: %s", image_id, exc)
        _mark_failed(image_id, error=str(exc)[:500])
        return ImageProcessingStatus.FAILED

    mark = result.fingerprint
    duplicate_of = _find_duplicate(image, mark)
    if duplicate_of is not None:
        # Повтор кадра не гоняем через нейросеть и не анализируем — решение всегда
        # `needs_review`: «вероятные дубли не удалять автоматически» (§5.2).
        render_key = _render_key(source_sha, ImageProcessingMode.TRIM if result.square else "none")
        return _commit(
            image,
            source_name=source_name,
            revision=revision,
            render_key=render_key,
            status=ImageProcessingStatus.NEEDS_REVIEW,
            mode=ImageProcessingMode.TRIM if result.square else "",
            square=result.square,
            fingerprint=mark,
            duplicate_of=duplicate_of,
            decision=ImageQcDecision.NEEDS_REVIEW,
            reasons=[image_quality.Reason.DUPLICATE],
            legacy_reason=ImageReviewReason.DUPLICATE,
            features={},
        )

    if result.kind == image_processing.ImageKind.BLANK:
        render_key = _render_key(source_sha, "empty")
        return _commit_empty(image, source_name, revision, render_key, mark)

    if result.kind == image_processing.ImageKind.OTHER:
        return _process_other(image, source_name, revision, raw, mark, rembg=rembg)

    if result.square is None:  # чёрный фон
        if not rembg:
            return _commit_pending_rembg(image, source_name, revision, mark)
        return _process_rembg_route(
            image,
            source_name,
            revision,
            raw,
            source_sha,
            route=image_quality.Route.REMBG_BLACK,
            mode=ImageProcessingMode.REMBG,
            fingerprint=mark,
            purpose_confirmed_subject=True,  # чёрный фон — штатный, проверенный маршрут
            release_to=release_to,
        )

    # WHITE/ALPHA с готовым квадратом (обрезка полей, без нейросети)
    return _process_trim_route(image, source_name, revision, raw, source_sha, result, mark)


def _process_other(
    image: ProductImage, source_name: str, revision: int, raw: bytes, mark: str, *, rembg: bool
) -> str:
    """Прочий фон: карточка с характеристиками, товар в кейсе, съёмка в работе.

    Автоматика такие фото не трогает вовсе (`SKIPPED`, без кандидата) — фон там
    часть кадра, а не подложка. Исключение — точечное действие человека
    «Предметное фото: подготовить удаление фона» (`manual_rembg_requested`),
    и только если назначение кадра не promo/kit/in_use (защита сцен и комплектов
    остаётся в силе даже при выставленном флаге, см. `request_manual_rembg`).
    """
    protected_purposes = (ImagePurpose.PROMO, ImagePurpose.KIT, ImagePurpose.IN_USE)
    if not image.manual_rembg_requested or image.purpose in protected_purposes:
        return _commit(
            image,
            source_name=source_name,
            revision=revision,
            render_key="",
            status=ImageProcessingStatus.SKIPPED,
            fingerprint=mark,
        )
    if not rembg:
        # Флаг стоит, но задача пришла из обычного воркера — ждём очередь rembg.
        return _commit_pending_rembg(image, source_name, revision, mark)
    return _process_rembg_route(
        image,
        source_name,
        revision,
        raw,
        hashlib.sha256(raw).hexdigest(),
        route=image_quality.Route.REMBG_MANUAL,
        mode=ImageProcessingMode.REMBG,
        fingerprint=mark,
        purpose_confirmed_subject=image.purpose in (ImagePurpose.WHOLE, ImagePurpose.DETAIL),
        release_to=ImageProcessingStatus.NEEDS_REMBG,
    )


def _process_trim_route(
    image: ProductImage,
    source_name: str,
    revision: int,
    raw: bytes,
    source_sha: str,
    result: image_processing.Result,
    mark: str,
) -> str:
    render_key = _render_key(source_sha, ImageProcessingMode.TRIM)
    square = result.square
    # Рамка содержимого В КООРДИНАТАХ ИСХОДНОГО кадра (до вписывания в квадрат) —
    # для касания края; квадрат уже с полями по построению, там его не измерить.
    source_img = image_processing.open_image(raw)
    source_rgb = (
        image_processing.flatten_on_white(source_img)
        if result.kind == image_processing.ImageKind.ALPHA
        else source_img.convert("RGB")
    )
    bbox = image_processing.content_bbox(source_rgb)
    square_rgb = image_processing.open_image(square.content).convert("RGB")
    product_share = (
        image_processing.product_share_for_size(bbox[2] - bbox[0], bbox[3] - bbox[1])
        if bbox
        else 0.0
    )
    features = image_quality.analyze(
        source_size=source_img.size,
        content_bbox=bbox,
        square=square,
        square_rgb=square_rgb,
        product_share=product_share,
    )
    verdict = image_quality.decide(
        features,
        route=image_quality.Route.TRIM,
        is_duplicate=False,
        is_empty=False,
        purpose_confirmed_subject=True,
    )
    return _apply_verdict(
        image,
        source_name=source_name,
        revision=revision,
        render_key=render_key,
        route=image_quality.Route.TRIM,
        mode=ImageProcessingMode.TRIM,
        square=square,
        fingerprint=mark,
        features=features,
        verdict=verdict,
    )


def _process_rembg_route(
    image: ProductImage,
    source_name: str,
    revision: int,
    raw: bytes,
    source_sha: str,
    *,
    route: str,
    mode: str,
    fingerprint: str,
    purpose_confirmed_subject: bool,
    release_to: str,
) -> str:
    render_key = _render_key(source_sha, route)
    if (
        image.candidate_render_key == render_key
        and image.qc_rules_version >= image_quality.QC_RULES_VERSION
    ):
        return "up_to_date"  # тот же исходник и маршрут — не зовём нейросеть повторно
    if not rembg_enabled() or not image_rembg.is_available():
        _release(image.pk, to=release_to)
        return "rembg_unavailable"
    source_img = image_processing.open_image(raw)
    rendered = image_rembg.render(source_img)
    if rendered is None:
        render_key_empty = _render_key(source_sha, f"{route}:empty")
        return _commit_empty(image, source_name, revision, render_key_empty, fingerprint)
    square, mask_bbox = rendered
    square_rgb = image_processing.open_image(square.content).convert("RGB")
    features = image_quality.analyze(
        source_size=source_img.size,
        content_bbox=mask_bbox,
        square=square,
        square_rgb=square_rgb,
        product_share=image_processing.product_share_for_size(
            mask_bbox[2] - mask_bbox[0], mask_bbox[3] - mask_bbox[1]
        ),
    )
    verdict = image_quality.decide(
        features,
        route=route,
        is_duplicate=False,
        is_empty=False,
        purpose_confirmed_subject=purpose_confirmed_subject,
    )
    return _apply_verdict(
        image,
        source_name=source_name,
        revision=revision,
        render_key=render_key,
        route=route,
        mode=mode,
        square=square,
        fingerprint=fingerprint,
        features=features,
        verdict=verdict,
    )


def _commit_pending_rembg(image, source_name, revision, fingerprint) -> str:
    return _commit(
        image,
        source_name=source_name,
        revision=revision,
        render_key="",
        status=ImageProcessingStatus.NEEDS_REMBG,
        fingerprint=fingerprint,
    )


def _commit_empty(image, source_name, revision, render_key, fingerprint) -> str:
    """Пустой результат (нет содержимого на кадре) — достоверный технический брак:
    контролёр отклоняет кандидата уверенно (§5.4). Байтов нет — архивировать нечего
    (§7.1: сбой до создания файла не изображается сохранённым фото)."""
    return _commit(
        image,
        source_name=source_name,
        revision=revision,
        render_key=render_key,
        status=ImageProcessingStatus.CANDIDATE_REJECTED,
        fingerprint=fingerprint,
        decision=ImageQcDecision.AUTO_REJECT_CANDIDATE,
        reasons=[image_quality.Reason.EMPTY],
        legacy_reason=ImageReviewReason.EMPTY,
        features={},
    )


_MAIN_FIT_BLOCKING_REASONS = {
    image_quality.Reason.TOUCHES_EDGE,
    image_quality.Reason.SUSPECT_BACKDROP,
    image_quality.Reason.SMALL,
    image_quality.Reason.DUPLICATE,
    image_quality.Reason.TORN,
}


def _main_fit_auto_for(purpose: str, reasons: list[str]) -> str:
    if purpose in (ImagePurpose.PROMO, ImagePurpose.IN_USE, ImagePurpose.KIT):
        return ImageMainFit.UNSUITABLE
    if set(reasons) & _MAIN_FIT_BLOCKING_REASONS:
        return ImageMainFit.UNSUITABLE
    return ImageMainFit.UNCHECKED


def _status_for_verdict(verdict: image_quality.Verdict, route: str) -> str:
    if verdict.decision == image_quality.Decision.AUTO_ACCEPT:
        return (
            ImageProcessingStatus.DONE
            if route in enabled_routes()
            else ImageProcessingStatus.OBSERVED
        )
    return ImageProcessingStatus.NEEDS_REVIEW


def _legacy_reason_for(reasons: list[str]) -> str:
    # Причин может быть несколько (`qc_reasons` — источник истины); в старое
    # одиночное поле `review_reason` (фильтр админки, устаревшая совместимость)
    # берём первую, у которой ЕСТЬ эквивалент, а не буквально первую в списке —
    # иначе `suspect_backdrop` (без legacy-эквивалента) молча вытеснял бы `small`.
    return next((_MAP_REASON_TO_LEGACY[r] for r in reasons if r in _MAP_REASON_TO_LEGACY), "")


def _apply_verdict(
    image: ProductImage,
    *,
    source_name: str,
    revision: int,
    render_key: str,
    route: str,
    mode: str,
    square: image_processing.Square,
    fingerprint: str,
    features: image_quality.Features,
    verdict: image_quality.Verdict,
) -> str:
    status = _status_for_verdict(verdict, route)
    features_dict = features.to_dict()
    features_dict["route"] = route  # нужен `redecide()` — реконструировать без перерисовки
    return _commit(
        image,
        source_name=source_name,
        revision=revision,
        render_key=render_key,
        status=status,
        mode=mode,
        square=square,
        fingerprint=fingerprint,
        decision=verdict.decision,
        reasons=verdict.reasons,
        legacy_reason=_legacy_reason_for(verdict.reasons),
        features=features_dict,
        main_fit_auto=_main_fit_auto_for(image.purpose, verdict.reasons),
        promote=status == ImageProcessingStatus.DONE,
    )


def redecide(image_id: int) -> str:
    """Пересчитать решение контролёра по СОХРАНЁННЫМ признакам (`qc_features`) —
    без перерисовки файла и без повторного вызова нейросети. Для случая, когда
    сменилась только версия правил контролёра (`QC_RULES_VERSION`), а не версия
    отрисовки: `process_product_images --redecide`.
    """
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is None:
        return "missing"
    if image.processing_status not in SETTLED or not image.qc_features:
        return "no_features"
    if image.qc_rules_version >= image_quality.QC_RULES_VERSION:
        return "up_to_date"

    data = dict(image.qc_features)
    route = data.pop("route", image_quality.Route.TRIM)
    features = image_quality.Features(
        source_width=data.get("source_width", 0),
        source_height=data.get("source_height", 0),
        content_width=data.get("content_width", 0),
        content_height=data.get("content_height", 0),
        touches_edge=data.get("touches_edge", False),
        product_share=data.get("product_share", 0.0),
        small=data.get("small", False),
        torn=data.get("torn", False),
        pale_content_share=data.get("pale_content_share"),
        suspect_backdrop=data.get("suspect_backdrop", False),
    )
    verdict = image_quality.decide(
        features,
        route=route,
        is_duplicate=image.review_reason == ImageReviewReason.DUPLICATE,
        is_empty=False,
        purpose_confirmed_subject=image.purpose in (ImagePurpose.WHOLE, ImagePurpose.DETAIL),
    )
    status = _status_for_verdict(verdict, route)
    revision = image.revision

    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=image_id).first()
        if (
            live is None
            or live.revision != revision
            or live.processing_status == ImageProcessingStatus.REJECTED
        ):
            return "stale"
        live.qc_decision = verdict.decision
        live.qc_reasons = verdict.reasons
        live.qc_rules_version = image_quality.QC_RULES_VERSION
        live.qc_decided_at = timezone.now()
        live.review_reason = _legacy_reason_for(verdict.reasons)
        live.main_fit_auto = _main_fit_auto_for(live.purpose, verdict.reasons)
        live.processing_status = status
        update_fields = [
            "qc_decision",
            "qc_reasons",
            "qc_rules_version",
            "qc_decided_at",
            "review_reason",
            "main_fit_auto",
            "processing_status",
        ]
        # Наблюдение → готово: маршрут за это время включили, файл менять не надо —
        # candidate и display уже одно и то же имя (см. `_commit`/`promote_observed`).
        if status == ImageProcessingStatus.DONE and live.candidate and not live.display:
            live.display = live.candidate.name
            live.display_checksum = live.candidate_checksum
            live.display_render_key = live.candidate_render_key
            update_fields += ["display", "display_checksum", "display_render_key"]
        live.save(update_fields=update_fields)
    return status


def _release(image_id: int, *, to: str = ImageProcessingStatus.NONE) -> None:
    """Задача вышла, ничего не сделав: `queued` возвращается, чтобы запись не зависла."""
    ProductImage.objects.filter(pk=image_id, processing_status=ImageProcessingStatus.QUEUED).update(
        processing_status=to
    )


def _mark_failed(image_id: int, *, error: str = "") -> None:
    """Ошибка обработки. Готовую принятую копию не стираем и с витрины не снимаем."""
    now = timezone.now()
    qs = ProductImage.objects.filter(pk=image_id).exclude(
        processing_status__in=(ImageProcessingStatus.DONE, ImageProcessingStatus.REJECTED)
    )
    qs.exclude(display="").update(
        processing_status=ImageProcessingStatus.DONE,
        attempts=F("attempts") + 1,
        last_error=error,
        processed_at=now,
    )
    qs.filter(display="").update(
        processing_status=ImageProcessingStatus.FAILED,
        attempts=F("attempts") + 1,
        last_error=error,
        processed_at=now,
    )


def _commit(
    image: ProductImage,
    *,
    source_name: str,
    revision: int,
    render_key: str,
    status: str,
    mode: str = "",
    square: image_processing.Square | None = None,
    fingerprint: str = "",
    duplicate_of: int | None = None,
    decision: str = "",
    reasons: list | None = None,
    legacy_reason: str = "",
    features: dict | None = None,
    main_fit_auto: str = ImageMainFit.UNCHECKED,
    promote: bool = False,
) -> str:
    """Записать кандидата/принятую копию под блокировкой со сверкой `revision`.

    `auto_reject_candidate` с байтами уходит в архив ДО открытия транзакции (сначала
    сохранность файла, потом переход статуса — §7.1); в public storage при этом
    ничего не пишется. Иначе файл (один и тот же и для `candidate`, и для `display`
    при промоушене — не плодим копий) пишется в public storage до транзакции.
    """
    storage = ProductImage._meta.get_field("display").storage
    new_name = ""
    digest = ""
    reject_now = decision == ImageQcDecision.AUTO_REJECT_CANDIDATE
    if square is not None and not reject_now:
        digest = hashlib.sha256(square.content).hexdigest()
        path = product_image_display_path(
            image, f"{image.pk}-{digest[:8]}-{render_key[:8] or 'v'}.webp"
        )
        new_name = storage.save(path, ContentFile(square.content))

    try:
        with transaction.atomic():
            live = ProductImage.objects.select_for_update().filter(pk=image.pk).first()
            if (
                live is None
                or live.image.name != source_name
                or live.processing_status == ImageProcessingStatus.REJECTED
                or live.revision != revision
                # старый воркер (меньшая PROCESSING_VERSION) не перезаписывает
                # результат, уже сделанный новым — деплой-race, отдельно от revision
                or live.processing_version > image_processing.PROCESSING_VERSION
            ):
                raise _Stale
            if (
                duplicate_of is not None
                and not ProductImage.objects.filter(pk=duplicate_of).exists()
            ):
                duplicate_of = None  # первый кадр успели удалить

            if decision == ImageQcDecision.AUTO_REJECT_CANDIDATE:
                # Байты этой попытки (если есть) или прежний кандидат записи (если
                # пересчёт превратил бывший кандидат в пустой результат) — в обоих
                # случаях отклонённое не выбрасывается молча, если байты существуют
                # (§7.1). Если байтов нет вовсе — архивной записи не будет: это не
                # сбой, а честный «сохранённое отклонение без файла».
                stale_bytes = None
                if square is None and live.candidate:
                    try:
                        with live.candidate.storage.open(live.candidate.name, "rb") as fh:
                            stale_bytes = fh.read()
                    except (OSError, FileNotFoundError):
                        stale_bytes = None
                content = square.content if square is not None else stale_bytes
                if content is not None:
                    archive_candidate(
                        live,
                        content=content,
                        checksum=hashlib.sha256(content).hexdigest(),
                        render_key=render_key,
                        processing_version=image_processing.PROCESSING_VERSION,
                        qc_rules_version=image_quality.QC_RULES_VERSION,
                        mode=mode,
                        reasons=reasons or [],
                        reason_text=", ".join(
                            image_quality.REASON_LABELS.get(r, r) for r in (reasons or [])
                        ),
                        source=ImageQcSource.AUTO,
                    )
                old_candidate = live.candidate.name or ""
                live.candidate = ""
                live.candidate_checksum = ""
                live.candidate_render_key = render_key
                live.candidate_mode = ""
                live.candidate_created_at = timezone.now()
                if old_candidate and old_candidate != new_name:
                    transaction.on_commit(lambda name=old_candidate: storage.delete(name))
            elif new_name:
                old_candidate = live.candidate.name or ""
                live.candidate = new_name
                live.candidate_checksum = digest
                live.candidate_render_key = render_key
                live.candidate_mode = mode
                live.candidate_created_at = timezone.now()
                if (
                    old_candidate
                    and old_candidate != new_name
                    and old_candidate != live.display.name
                ):
                    transaction.on_commit(lambda name=old_candidate: storage.delete(name))

            live.processing_status = status
            live.processing_mode = mode
            live.processing_version = image_processing.PROCESSING_VERSION
            live.processed_at = timezone.now()
            live.review_reason = legacy_reason
            live.duplicate_of_id = duplicate_of
            live.fingerprint = fingerprint
            live.qc_decision = decision
            live.qc_source = ImageQcSource.AUTO if decision else live.qc_source
            live.qc_rules_version = (
                image_quality.QC_RULES_VERSION if decision else live.qc_rules_version
            )
            live.qc_features = features or {}
            live.qc_reasons = reasons or []
            live.qc_decided_at = timezone.now() if decision else live.qc_decided_at
            live.main_fit_auto = main_fit_auto

            if promote and new_name:
                old_display = live.display.name or ""
                live.display = new_name
                live.display_checksum = digest
                live.display_render_key = render_key
                if old_display and old_display != new_name:
                    transaction.on_commit(lambda name=old_display: storage.delete(name))

            live.save(update_fields=list(ProductImage.PROCESSING_FIELDS))
    except _Stale:
        if new_name:
            storage.delete(new_name)
        return "stale"
    if decision:
        _log_event(
            live,
            kind=ProductImageEvent.Kind.QC_DECISION,
            source=ImageQcSource.AUTO,
            render_key=render_key,
            checksum=digest,
            after={"status": status, "decision": decision},
            reasons=reasons or [],
        )
    return status


def _find_duplicate(image: ProductImage, mark: str) -> int | None:
    """Другое фото этого товара с тем же кадром — по всем фото в БД, не только
    в текущей пачке обработки. Сами дубли в поиске не участвуют."""
    if not mark:
        return None
    others = (
        ProductImage.objects.filter(product_id=image.product_id, duplicate_of__isnull=True)
        .exclude(pk=image.pk)
        .exclude(fingerprint="")
        .order_by("pk")
        .values_list("pk", "fingerprint")
    )
    return next((pk for pk, other in others if image_processing.is_duplicate(mark, other)), None)


# --- решения человека (админка) ------------------------------------------------


def _bump_revision(image_id: int) -> int | None:
    """Атомарно поднять ревизию, вернуть новое значение (или None — записи нет)."""
    updated = ProductImage.objects.filter(pk=image_id).update(revision=F("revision") + 1)
    if not updated:
        return None
    return ProductImage.objects.filter(pk=image_id).values_list("revision", flat=True).first()


def promote_observed(*, routes: frozenset[str] | None = None) -> int:
    """Маршрут только что включили в `PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES` — опубликовать
    уже готовых кандидатов в `observed` без повторной отрисовки и без нейросети.

    Не идёт через `_process`: решение контролёра (`auto_accept`) уже вынесено и
    хранится в `qc_decision`, пересчитывать признаки незачем. `candidate_mode`
    записи должен совпадать с одним из включаемых маршрутов.
    """
    active_routes = routes if routes is not None else enabled_routes()
    mode_by_route = {
        image_quality.Route.TRIM: ImageProcessingMode.TRIM,
        image_quality.Route.REMBG_BLACK: ImageProcessingMode.REMBG,
        image_quality.Route.REMBG_MANUAL: ImageProcessingMode.REMBG,
    }
    modes = {mode_by_route[r] for r in active_routes if r in mode_by_route}
    if not modes:
        return 0
    storage = ProductImage._meta.get_field("display").storage
    candidates = ProductImage.objects.filter(
        processing_status=ImageProcessingStatus.OBSERVED,
        qc_decision=ImageQcDecision.AUTO_ACCEPT,
        candidate_mode__in=modes,
    ).exclude(candidate="")
    promoted = 0
    for image_id in list(candidates.values_list("pk", flat=True)):
        with transaction.atomic():
            live = (
                ProductImage.objects.select_for_update()
                .filter(pk=image_id, processing_status=ImageProcessingStatus.OBSERVED)
                .first()
            )
            if live is None or not live.candidate:
                continue
            old_display = live.display.name or ""
            live.display = live.candidate.name
            live.display_checksum = live.candidate_checksum
            live.display_render_key = live.candidate_render_key
            live.processing_status = ImageProcessingStatus.DONE
            live.save(
                update_fields=[
                    "display",
                    "display_checksum",
                    "display_render_key",
                    "processing_status",
                ]
            )
            if old_display and old_display != live.display.name:
                transaction.on_commit(lambda name=old_display: storage.delete(name))
        _log_event(
            live,
            kind=ProductImageEvent.Kind.QC_DECISION,
            source=ImageQcSource.AUTO,
            render_key=live.candidate_render_key,
            note="promote_observed",
        )
        promoted += 1
    return promoted


def reprocess(image_id: int, *, actor=None) -> bool:
    """«Обработать заново»: сбросить итог — в том числе «оставлен оригинал» — и в очередь."""
    new_revision = _bump_revision(image_id)
    if new_revision is None:
        return False
    previous = (
        ProductImage.objects.filter(pk=image_id).values_list("processing_status", flat=True).first()
    )
    if previous is None or previous == ImageProcessingStatus.QUEUED:
        return False
    ProductImage.objects.filter(pk=image_id, processing_status=previous).update(
        processing_status=ImageProcessingStatus.NONE
    )
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is not None:
        _log_event(
            image, kind=ProductImageEvent.Kind.REPROCESS, source=ImageQcSource.HUMAN, actor=actor
        )
    if enqueue(image_id):
        return True
    ProductImage.objects.filter(pk=image_id, processing_status=ImageProcessingStatus.NONE).update(
        processing_status=previous
    )
    return False


def revert_to_original(image_id: int, *, actor=None) -> bool:
    """«Вернуть оригинал»: убрать кандидата/копию и запомнить решение — автоматика
    больше не тронет исходник. Ожидающий кандидат сначала уходит в архив (§7.1):
    решение «оставить оригинал» по смыслу отклоняет его, а не просто прячет.
    """
    storage = ProductImage._meta.get_field("display").storage
    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=image_id).first()
        if live is None:
            return False
        before = {"processing_status": live.processing_status}
        if live.candidate:
            try:
                with live.candidate.open("rb") as fh:
                    content = fh.read()
                archive_candidate(
                    live,
                    content=content,
                    checksum=live.candidate_checksum or hashlib.sha256(content).hexdigest(),
                    render_key=live.candidate_render_key,
                    processing_version=live.processing_version,
                    qc_rules_version=live.qc_rules_version,
                    mode=live.candidate_mode,
                    reasons=list(live.qc_reasons or []),
                    reason_text="Оставлен оригинал: кандидат отклонён вручную",
                    source=ImageQcSource.HUMAN,
                    actor=actor,
                )
            except (OSError, FileNotFoundError):
                log.warning("фото %s: файл кандидата не читается при возврате оригинала", image_id)
        old_display = live.display.name or ""
        old_candidate = live.candidate.name or ""
        live.display = ""
        live.display_checksum = ""
        live.display_render_key = ""
        live.candidate = ""
        live.candidate_checksum = ""
        live.candidate_render_key = ""
        live.candidate_mode = ""
        live.candidate_created_at = None
        live.processing_status = ImageProcessingStatus.REJECTED
        live.processing_mode = ""
        live.qc_decision = ""
        live.qc_source = ImageQcSource.HUMAN
        # Повтор кадра — исключение: вопрос про оригинал, а не про копию, и
        # `duplicate_of`/`fingerprint` остаются — иначе на проверку ушёл бы уже
        # первый кадр пары вместо второго.
        if live.review_reason != ImageReviewReason.DUPLICATE:
            live.review_reason = ""
        live.processed_at = timezone.now()
        live.save(update_fields=list(ProductImage.PROCESSING_FIELDS))
        if old_display and old_display != old_candidate:
            transaction.on_commit(lambda: storage.delete(old_display))
        if old_candidate:
            transaction.on_commit(lambda: storage.delete(old_candidate))
    ProductImage.objects.filter(pk=image_id).update(revision=F("revision") + 1)
    _log_event(
        live,
        kind=ProductImageEvent.Kind.REVERT_ORIGINAL,
        source=ImageQcSource.HUMAN,
        actor=actor,
        before=before,
        after={"processing_status": ImageProcessingStatus.REJECTED},
    )
    return True


def accept_candidate(
    image_id: int, *, expected_checksum: str, expected_revision: int, actor=None
) -> bool:
    """Принять КОНКРЕТНОГО кандидата: сверка checksum/revision защищает от публикации
    файла, который модератор не видел (кандидат мог смениться между открытием
    страницы и кликом). Массового «принять» намеренно нет."""
    storage = ProductImage._meta.get_field("display").storage
    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=image_id).first()
        if (
            live is None
            or not live.candidate
            or live.candidate_checksum != expected_checksum
            or live.revision != expected_revision
        ):
            return False
        old_display = live.display.name or ""
        live.display = live.candidate.name
        live.display_checksum = live.candidate_checksum
        live.display_render_key = live.candidate_render_key
        live.processing_status = ImageProcessingStatus.DONE
        live.qc_source = ImageQcSource.HUMAN
        live.revision = F("revision") + 1
        live.save(
            update_fields=[
                "display",
                "display_checksum",
                "display_render_key",
                "processing_status",
                "qc_source",
                "revision",
            ]
        )
        if old_display and old_display != live.candidate.name:
            transaction.on_commit(lambda: storage.delete(old_display))
    _log_event(
        live,
        kind=ProductImageEvent.Kind.ACCEPT_CANDIDATE,
        source=ImageQcSource.HUMAN,
        actor=actor,
        checksum=expected_checksum,
        render_key=live.candidate_render_key,
    )
    return True


def reject_candidate(
    image_id: int,
    *,
    expected_checksum: str,
    expected_revision: int,
    reason_text: str = "",
    actor=None,
) -> bool:
    """Отклонить кандидата вручную: байты уходят в архив, витрина не меняется.

    Не путать с `revert_to_original` — тот ещё и запрещает автообработку исходника
    (`REJECTED`). Здесь запись возвращается в `CANDIDATE_REJECTED`: новая обработка
    (другой исходник/параметры/версия правил) может предложить кандидата снова.
    """
    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=image_id).first()
        if (
            live is None
            or not live.candidate
            or live.candidate_checksum != expected_checksum
            or live.revision != expected_revision
        ):
            return False
        try:
            with live.candidate.open("rb") as fh:
                content = fh.read()
        except (OSError, FileNotFoundError):
            log.warning("фото %s: файл кандидата не читается при ручном отклонении", image_id)
            return False
        archive_candidate(
            live,
            content=content,
            checksum=expected_checksum,
            render_key=live.candidate_render_key,
            processing_version=live.processing_version,
            qc_rules_version=live.qc_rules_version,
            mode=live.candidate_mode,
            reasons=list(live.qc_reasons or []),
            reason_text=reason_text or "Отклонено вручную",
            source=ImageQcSource.HUMAN,
            actor=actor,
        )
        old_candidate = live.candidate.name
        live.candidate = ""
        live.candidate_checksum = ""
        live.processing_status = ImageProcessingStatus.CANDIDATE_REJECTED
        live.qc_decision = ImageQcDecision.AUTO_REJECT_CANDIDATE
        live.qc_source = ImageQcSource.HUMAN
        live.revision = F("revision") + 1
        live.save(
            update_fields=[
                "candidate",
                "candidate_checksum",
                "processing_status",
                "qc_decision",
                "qc_source",
                "revision",
            ]
        )
        transaction.on_commit(lambda: live.display.storage.delete(old_candidate))
    _log_event(
        live,
        kind=ProductImageEvent.Kind.REJECT_CANDIDATE,
        source=ImageQcSource.HUMAN,
        actor=actor,
        checksum=expected_checksum,
        note=reason_text,
    )
    return True


def set_purpose(image_id: int, purpose: str, *, actor=None) -> bool:
    new_revision = _bump_revision(image_id)
    if new_revision is None:
        return False
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is None:
        return False
    before = {"purpose": image.purpose}
    protected = purpose in (ImagePurpose.PROMO, ImagePurpose.KIT, ImagePurpose.IN_USE)
    ProductImage.objects.filter(pk=image_id).update(
        purpose=purpose, manual_rembg_requested=False if protected else F("manual_rembg_requested")
    )
    image.refresh_from_db(fields=["purpose"])
    _log_event(
        image,
        kind=ProductImageEvent.Kind.SET_PURPOSE,
        source=ImageQcSource.HUMAN,
        actor=actor,
        before=before,
        after={"purpose": purpose},
    )
    return True


def set_main_fit(image_id: int, fit: str, *, reason: str = "", actor=None) -> bool:
    updated = ProductImage.objects.filter(pk=image_id).update(
        main_fit_human=fit, main_fit_reason=reason, revision=F("revision") + 1
    )
    if not updated:
        return False
    image = ProductImage.objects.filter(pk=image_id).first()
    _log_event(
        image,
        kind=ProductImageEvent.Kind.SET_MAIN_FIT,
        source=ImageQcSource.HUMAN,
        actor=actor,
        after={"main_fit_human": fit, "main_fit_reason": reason},
    )
    return True


def set_main(image_id: int, *, actor=None) -> bool:
    """Назначить главным атомарно: строго одно `is_main=True` на товар."""
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is None:
        return False
    with transaction.atomic():
        (
            ProductImage.objects.select_for_update()
            .filter(product_id=image.product_id, is_main=True)
            .exclude(pk=image_id)
            .update(is_main=False)
        )
        ProductImage.objects.filter(pk=image_id).update(is_main=True)
    _log_event(image, kind=ProductImageEvent.Kind.SET_MAIN, source=ImageQcSource.HUMAN, actor=actor)
    return True


def request_manual_rembg(image_id: int, *, actor=None) -> str:
    """«Предметное фото: подготовить удаление фона» — точечное действие человека.

    Возвращает код результата: `ok`, `not_found`, `not_other_background` (кадр не
    классифицирован как прочий фон — действие для чёрного фона не нужно, он и так
    идёт по маршруту `rembg_black`), `protected_purpose` (сцена/комплект/реклама —
    защиту не снимаем даже по явному клику, сначала нужно сменить назначение).
    """
    image = ProductImage.objects.filter(pk=image_id).first()
    if image is None:
        return "not_found"
    if image.processing_status != ImageProcessingStatus.SKIPPED:
        return "not_other_background"
    if image.purpose in (ImagePurpose.PROMO, ImagePurpose.KIT, ImagePurpose.IN_USE):
        return "protected_purpose"
    new_revision = _bump_revision(image_id)
    if new_revision is None:
        return "not_found"
    ProductImage.objects.filter(pk=image_id).update(
        manual_rembg_requested=True, processing_status=ImageProcessingStatus.NONE
    )
    _log_event(
        image,
        kind=ProductImageEvent.Kind.MANUAL_REMBG_REQUESTED,
        source=ImageQcSource.HUMAN,
        actor=actor,
    )
    enqueue(image_id, rembg=True)
    return "ok"


def return_candidate_to_review(archive_id: int, *, actor=None) -> bool:
    """Вернуть отклонённого кандидата на проверку из архива (§7.1).

    Само по себе НЕ публикует файл — дальше решает обычный `accept_candidate`.
    Работает только если исходник записи не менялся с момента отклонения (иначе
    архивный файл относится уже к другому кадру) и если у записи сейчас нет
    более свежего кандидата (не подменяем то, что уже ждёт решения).
    """
    archive = RejectedImageCandidate.objects.filter(pk=archive_id).first()
    if archive is None or archive.image_id is None:
        return False
    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=archive.image_id).first()
        if live is None:
            return False
        if (archive.product_snapshot or {}).get("original_image") != (live.image.name or ""):
            return False
        if live.candidate or live.processing_status == ImageProcessingStatus.QUEUED:
            return False
        try:
            with archive.file.open("rb") as fh:
                content = fh.read()
        except (OSError, FileNotFoundError):
            return False
        storage = ProductImage._meta.get_field("display").storage
        path = product_image_display_path(live, f"{live.pk}-{archive.checksum[:8]}-return.webp")
        new_name = storage.save(path, ContentFile(content))
        live.candidate = new_name
        live.candidate_checksum = archive.checksum
        live.candidate_render_key = archive.render_key
        live.candidate_mode = archive.mode
        live.candidate_created_at = timezone.now()
        live.processing_status = ImageProcessingStatus.NEEDS_REVIEW
        live.qc_decision = ImageQcDecision.NEEDS_REVIEW
        live.qc_source = ImageQcSource.HUMAN
        live.qc_reasons = list(archive.reasons or [])
        live.revision = F("revision") + 1
        live.save(
            update_fields=[
                "candidate",
                "candidate_checksum",
                "candidate_render_key",
                "candidate_mode",
                "candidate_created_at",
                "processing_status",
                "qc_decision",
                "qc_source",
                "qc_reasons",
                "revision",
            ]
        )
        archive.status = RejectedImageCandidate.Status.RETURNED
        archive.save(update_fields=["status"])
    _log_event(
        live,
        kind=ProductImageEvent.Kind.RETURN_TO_REVIEW,
        source=ImageQcSource.HUMAN,
        actor=actor,
        render_key=archive.render_key,
        checksum=archive.checksum,
    )
    return True
