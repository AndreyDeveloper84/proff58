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

from . import image_processing
from .models import (
    ImageProcessingMode,
    ImageProcessingStatus,
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
) -> bool:
    """Пометить «в очереди» и отправить задачу. False — не подошёл статус или упал брокер.

    `outdated` добавляет готовые записи только со старой версией параметров — иначе
    запись, которую воркер успел обработать после выборки, ушла бы в очередь повторно.
    """
    from .tasks import process_product_image

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
        process_product_image.delay(image_id)
    except Exception:
        log.exception("фото %s: задача не поставлена в очередь", image_id)
        ProductImage.objects.filter(
            pk=image_id, processing_status=ImageProcessingStatus.QUEUED
        ).update(processing_status=previous)
        return False
    return True


# --- обработка ---------------------------------------------------------------


def process_image(image_id: int) -> str:
    """Сделать витринную копию. Возвращает итог: статус или причину пропуска."""
    try:
        return _process(image_id)
    except Exception:
        log.exception("фото %s: обработка упала", image_id)
        _mark_failed(image_id)
        return ImageProcessingStatus.FAILED


def _process(image_id: int) -> str:
    image = ProductImage.objects.select_related("product").filter(pk=image_id).first()
    if image is None:
        return "missing"
    if not is_enabled(FLAG):
        _release(image_id)
        return "disabled"
    if image.product.content_locked:
        _release(image_id)
        return "content_locked"
    if image.processing_status == ImageProcessingStatus.REJECTED:
        return "rejected"
    if (
        image.processing_status in SETTLED
        and image.processing_version >= image_processing.PROCESSING_VERSION
    ):
        return "up_to_date"
    if not image.image:
        _release(image_id)
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

    if result.content is None:
        status = (
            ImageProcessingStatus.NEEDS_REVIEW
            if result.kind == image_processing.ImageKind.BLANK
            else ImageProcessingStatus.NEEDS_REMBG
        )
        return _commit(image, source_name, status=status)
    return _commit(
        image,
        source_name,
        status=ImageProcessingStatus.DONE,
        mode=ImageProcessingMode.TRIM,
        content=result.content,
    )


def _release(image_id: int) -> None:
    """Задача вышла, ничего не сделав: `queued` → `none`, чтобы запись не зависла."""
    ProductImage.objects.filter(pk=image_id, processing_status=ImageProcessingStatus.QUEUED).update(
        processing_status=ImageProcessingStatus.NONE
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
    content: bytes | None = None,
) -> str:
    version = image_processing.PROCESSING_VERSION
    storage = ProductImage._meta.get_field("display").storage
    new_name = ""
    digest = ""
    if content is not None:
        digest = hashlib.sha256(content).hexdigest()
        path = product_image_display_path(image, f"{image.pk}-{digest[:8]}-v{version}.webp")
        new_name = storage.save(path, ContentFile(content))

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
