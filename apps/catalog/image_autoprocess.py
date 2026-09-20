"""Автообработка фото товара: запись витринной копии в `ProductImage` (ADR-0014).

Здесь всё, что касается БД и storage; сама обработка байтов — `image_processing`.

Требования ADR-0014, которые держит этот модуль:

- исходный `image` и его `checksum` не трогаются никогда;
- файл копии пишется ДО транзакции (storage не откатывается), запись обновляется
  под `select_for_update` со сверкой имени оригинала и версии параметров. Если запись
  удалили, фото заменили, менеджер оставил оригинал или уже есть копия новее — свой
  файл удаляем, запись не трогаем (обычный `save()` после удаления откатом сделал бы
  INSERT и «воскресил» её);
- только `save(update_fields=...)`, старая копия удаляется после коммита;
- `rejected` и товары с `content_locked` не трогаются.

Статус `queued` не должен зависать: ранний выход задачи возвращает его в `none`,
любая ошибка даёт `failed`, а готовая копия при сбое не стирается.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.features import is_enabled

from . import image_processing, image_rembg
from .models import (
    ImageProcessingMode,
    ImageProcessingStatus,
    ImageReviewReason,
    ProductImage,
    product_image_display_path,
)

log = logging.getLogger(__name__)

FLAG = "product_image_autoprocess"

#: Итоговые статусы: при текущей версии параметров повторно не обрабатываем.
SETTLED = (
    ImageProcessingStatus.DONE,
    ImageProcessingStatus.NEEDS_REMBG,
    ImageProcessingStatus.NEEDS_REVIEW,
    ImageProcessingStatus.SKIPPED,
)


class _Stale(Exception):
    """Запись удалили, фото заменили или решение уже принято, пока шла обработка."""


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
) -> bool:
    """Пометить «в очереди» и отправить задачу. False — не подошёл статус или упал брокер.

    `outdated` добавляет готовые записи только со старой версией параметров — иначе
    запись, которую воркер успел обработать после выборки, ушла бы в очередь повторно.
    `rembg` — задача в очередь `rembg` (сервис `celery-rembg`, поднимается на бэкфилл).
    """
    from .tasks import process_product_image, remove_photo_background

    task = remove_photo_background if rembg else process_product_image

    match = Q(processing_status__in=statuses)
    if outdated:
        match |= Q(
            processing_status__in=SETTLED,
            processing_version__lt=image_processing.PROCESSING_VERSION,
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
        task.delay(image_id)
    except Exception:
        log.exception("фото %s: задача не поставлена в очередь", image_id)
        ProductImage.objects.filter(
            pk=image_id, processing_status=ImageProcessingStatus.QUEUED
        ).update(processing_status=previous)
        return False
    return True


# --- обработка ---------------------------------------------------------------


def process_image(image_id: int, *, rembg: bool = False) -> str:
    """Сделать витринную копию. Возвращает итог: статус или причину пропуска.

    `rembg=True` — задача сервиса нейросети: чёрный фон обрабатывается удалением
    фона, а не откладывается в `needs_rembg`. Прочий фон не трогается в обоих
    режимах — он уходит в `skipped`.
    """
    try:
        return _process(image_id, rembg=rembg)
    except Exception:
        log.exception("фото %s: обработка упала", image_id)
        _mark_failed(image_id)
        return ImageProcessingStatus.FAILED


def _process(image_id: int, *, rembg: bool = False) -> str:
    # задача нейросети, вышедшая без работы, возвращает фото в «ждёт нейросеть»
    release_to = ImageProcessingStatus.NEEDS_REMBG if rembg else ImageProcessingStatus.NONE
    image = ProductImage.objects.select_related("product").filter(pk=image_id).first()
    if image is None:
        return "missing"
    if not is_enabled(FLAG):
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
    ):
        return "up_to_date"
    if not image.image:
        _release(image_id, to=release_to)
        return "no_file"

    source_name = image.image.name
    try:
        with image.image.storage.open(source_name, "rb") as fh:
            raw = fh.read()
        result = image_processing.process(raw)
    except (OSError, image_processing.UnreadableImage) as exc:
        log.warning("фото %s не обработано: %s", image_id, exc)
        _mark_failed(image_id)
        return ImageProcessingStatus.FAILED

    mark = result.fingerprint
    duplicate_of = _find_duplicate(image, mark)
    if duplicate_of is not None:
        # повтор кадра не гоняем через нейросеть: решение за менеджером
        return _commit(
            image,
            source_name,
            status=ImageProcessingStatus.NEEDS_REVIEW,
            reason=ImageReviewReason.DUPLICATE,
            duplicate_of=duplicate_of,
            fingerprint=mark,
            mode=ImageProcessingMode.TRIM if result.square else "",
            square=result.square,
        )
    if result.kind == image_processing.ImageKind.BLANK:
        return _commit(
            image,
            source_name,
            status=ImageProcessingStatus.NEEDS_REVIEW,
            reason=ImageReviewReason.EMPTY,
            fingerprint=mark,
        )
    if result.kind == image_processing.ImageKind.OTHER:
        # Прочий фон — карточка с характеристиками, товар в кейсе, съёмка в работе:
        # фон там часть кадра. Нейросеть вырезала бы из него один инструмент,
        # выбросив текст и комплектацию (просмотр 45 копий стенда 20.09.2026).
        # Проверка стоит выше ветки нейросети намеренно: воркер rembg приходит
        # сюда же и такие фото тоже не трогает.
        return _commit(image, source_name, status=ImageProcessingStatus.SKIPPED, fingerprint=mark)
    if result.square is None and not rembg:
        return _commit(
            image, source_name, status=ImageProcessingStatus.NEEDS_REMBG, fingerprint=mark
        )
    if result.square is None:
        return _process_with_rembg(image, source_name, raw, result, release_to)
    return _commit_square(
        image, source_name, result.square, mode=ImageProcessingMode.TRIM, fingerprint=mark
    )


def _process_with_rembg(
    image: ProductImage,
    source_name: str,
    raw: bytes,
    result: image_processing.Result,
    release_to: str,
) -> str:
    """Чёрный фон — на витрину; разорванная вырезка — на проверку менеджеру."""
    if result.kind != image_processing.ImageKind.BLACK:
        # Сюда доходит только чёрный фон. Страховка, а не комментарий: функцию
        # зовут из двух режимов, и ошибка в порядке проверок выше означала бы
        # съеденную карточку на витрине.
        return _commit(
            image, source_name, status=ImageProcessingStatus.SKIPPED, fingerprint=result.fingerprint
        )
    if not image_rembg.is_available():
        _release(image.pk, to=release_to)
        return "rembg_unavailable"
    square = image_rembg.render(image_processing.open_image(raw))
    if square is None:  # нейросеть товар не нашла
        return _commit(
            image,
            source_name,
            status=ImageProcessingStatus.NEEDS_REVIEW,
            reason=ImageReviewReason.EMPTY,
            fingerprint=result.fingerprint,
        )
    return _commit_square(
        image,
        source_name,
        square,
        mode=ImageProcessingMode.REMBG,
        fingerprint=result.fingerprint,
        # распалась на куски — нейросеть съела текст карточки: смотрит человек
        reason=ImageReviewReason.TORN if square.torn else "",
    )


def _commit_square(
    image: ProductImage,
    source_name: str,
    square: image_processing.Square,
    *,
    mode: str,
    fingerprint: str,
    reason: str = "",
) -> str:
    """Готовая копия: на витрину, если к ней нет вопросов, иначе на проверку.

    Рвань важнее мелкоты: у разорванной копии «мелким» оказывается уцелевший
    огрызок, и причина «мелкое фото» увела бы менеджера не туда.
    """
    if square.small and not reason:
        reason = ImageReviewReason.SMALL
    return _commit(
        image,
        source_name,
        status=ImageProcessingStatus.NEEDS_REVIEW if reason else ImageProcessingStatus.DONE,
        reason=reason,
        fingerprint=fingerprint,
        mode=mode,
        square=square,
    )


def _find_duplicate(image: ProductImage, mark: str) -> int | None:
    """Другое фото этого товара с тем же кадром. Сами дубли в поиске не участвуют.

    Поэтому из пары одинаковых кадров помечается ровно один — тот, что
    обработан вторым (при бэкфилле — позже загруженный).
    """
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


def _release(image_id: int, *, to: str = ImageProcessingStatus.NONE) -> None:
    """Задача вышла, ничего не сделав: `queued` возвращается, чтобы запись не зависла."""
    ProductImage.objects.filter(pk=image_id, processing_status=ImageProcessingStatus.QUEUED).update(
        processing_status=to
    )


def _mark_failed(image_id: int) -> None:
    """Ошибка обработки. Готовую копию не стираем и с витрины не снимаем.

    Временный сбой чтения при пересоздании копий (`--outdated`) не должен убирать
    хорошее фото: запись с копией возвращается в `done` со старой версией.
    """
    active = ProductImage.objects.filter(pk=image_id).exclude(
        processing_status__in=(ImageProcessingStatus.DONE, ImageProcessingStatus.REJECTED)
    )
    active.exclude(display="").update(processing_status=ImageProcessingStatus.DONE)
    active.filter(display="").update(
        processing_status=ImageProcessingStatus.FAILED, processed_at=timezone.now()
    )


def _commit(
    image: ProductImage,
    source_name: str,
    *,
    status: str,
    mode: str = "",
    square: image_processing.Square | None = None,
    reason: str = "",
    duplicate_of: int | None = None,
    fingerprint: str = "",
) -> str:
    version = image_processing.PROCESSING_VERSION
    storage = ProductImage._meta.get_field("display").storage
    new_name = ""
    digest = ""
    if square is not None:
        digest = hashlib.sha256(square.content).hexdigest()
        path = product_image_display_path(image, f"{image.pk}-{digest[:8]}-v{version}.webp")
        new_name = storage.save(path, ContentFile(square.content))

    try:
        with transaction.atomic():
            live = ProductImage.objects.select_for_update().filter(pk=image.pk).first()
            if (
                live is None
                or live.image.name != source_name
                or live.processing_status == ImageProcessingStatus.REJECTED
                # старый воркер после деплоя не перезаписывает копию новой версии
                or live.processing_version > version
            ):
                raise _Stale
            old_display = live.display.name or ""
            live.display = new_name
            live.display_checksum = digest
            live.processing_status = status
            live.processing_mode = mode
            live.processing_version = version
            live.processed_at = timezone.now()
            live.review_reason = reason
            if (
                duplicate_of is not None
                and not ProductImage.objects.filter(pk=duplicate_of).exists()
            ):
                duplicate_of = None  # первый кадр успели удалить
            live.duplicate_of_id = duplicate_of
            live.fingerprint = fingerprint
            live.save(update_fields=list(ProductImage.PROCESSING_FIELDS))
            if old_display and old_display != new_name:
                transaction.on_commit(lambda: storage.delete(old_display))
    except _Stale:
        if new_name:
            storage.delete(new_name)
        return "stale"
    return status


# --- действия менеджера (админка) ----------------------------------------------------


def reprocess(image_id: int) -> bool:
    """«Обработать заново»: сбросить итог — в том числе «оставлен оригинал» — и в очередь.

    Пока фото в очереди, витрина показывает оригинал; готовая копия заменит прежнюю.
    Если задачу поставить не удалось, прежний статус возвращается.
    """
    previous = (
        ProductImage.objects.filter(pk=image_id).values_list("processing_status", flat=True).first()
    )
    if previous is None or previous == ImageProcessingStatus.QUEUED:
        return False
    ProductImage.objects.filter(pk=image_id, processing_status=previous).update(
        processing_status=ImageProcessingStatus.NONE
    )
    if enqueue(image_id):
        return True
    ProductImage.objects.filter(pk=image_id, processing_status=ImageProcessingStatus.NONE).update(
        processing_status=previous
    )
    return False


def revert_to_original(image_id: int) -> bool:
    """«Вернуть оригинал»: убрать копию и запомнить решение — автоматика её не вернёт.

    Под блокировкой записи: идущая в этот момент задача увидит `rejected` в `_commit`
    и свою копию не запишет. Файл копии удаляется после коммита.
    """
    storage = ProductImage._meta.get_field("display").storage
    with transaction.atomic():
        live = ProductImage.objects.select_for_update().filter(pk=image_id).first()
        if live is None:
            return False
        old_display = live.display.name or ""
        live.display = ""
        live.display_checksum = ""
        live.processing_status = ImageProcessingStatus.REJECTED
        live.processing_mode = ""
        # Вопросы к копии умерли вместе с копией. Повтор кадра — исключение:
        # он про оригинал, а не про копию, и `duplicate_of` с `fingerprint`
        # остаются. Сбросить их значило бы вернуть запись в поиск дублей, и
        # на проверку ушёл бы уже первый кадр пары вместо второго.
        if live.review_reason != ImageReviewReason.DUPLICATE:
            live.review_reason = ""
        live.processed_at = timezone.now()
        live.save(update_fields=list(ProductImage.PROCESSING_FIELDS))
        if old_display:
            transaction.on_commit(lambda: storage.delete(old_display))
    return True


def accept_review(image_id: int) -> bool:
    """«Принять копию»: кандидат на проверке уходит на витрину."""
    return bool(
        ProductImage.objects.filter(
            pk=image_id, processing_status=ImageProcessingStatus.NEEDS_REVIEW
        )
        .exclude(display="")
        .update(processing_status=ImageProcessingStatus.DONE)
    )
