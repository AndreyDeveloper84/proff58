"""Архив отклонённых кандидатов фото (§7.1 доработки ADR-0014).

Хранит именно байты отклонённого кандидата в закрытом хранилище
(`RejectedImageCandidate.file`, вне `/media/`) — отдельно от статуса `ProductImage`.
Повторная обработка с тем же исходником/параметрами/маршрутом не плодит копию
(`uniq_rejected_candidate_render`). Ни автоочистки, ни срока хранения здесь нет —
решение о судьбе файлов принимает владелец отдельно от этой доработки.
"""

from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from .models import RejectedImageCandidate

log = logging.getLogger(__name__)


def _product_snapshot(image) -> dict:
    product = image.product
    return {
        "product_id": product.pk,
        "product_name": getattr(product, "name", ""),
        "code_1c": getattr(product, "code_1c", ""),
        "article": getattr(product, "article", ""),
        "image_source": image.source,
        "source_url": image.source_url or "",
        "original_image": image.image.name or "",
    }


def archive_candidate(
    image,
    *,
    content: bytes,
    checksum: str,
    render_key: str,
    processing_version: int,
    qc_rules_version: int,
    mode: str,
    reasons: list,
    reason_text: str,
    source: str,
    actor=None,
) -> RejectedImageCandidate | None:
    """Сохранить байты отклонённого кандидата (идемпотентно по image+render_key+checksum).

    Вызывается изнутри уже открытой транзакции записи `ProductImage` (`_commit`,
    `revert_to_original`, `reject_candidate`). Сначала пишется файл, потом строка
    архива: при сбое между ними на диске остаётся файл без записи (безопасно —
    аудит найдёт его как orphan), а не запись без файла.
    """
    existing = RejectedImageCandidate.objects.filter(
        image_ref=image.pk, render_key=render_key, checksum=checksum
    ).first()
    if existing is not None:
        return existing

    storage = RejectedImageCandidate._meta.get_field("file").storage
    path = f"{image.product_id}/{image.pk}-{checksum[:12]}.webp"
    saved_name = storage.save(path, ContentFile(content))
    try:
        # Savepoint: гонка (два прогона одновременно создали одинаковый кандидат)
        # не должна отравить внешнюю транзакцию записи ProductImage.
        with transaction.atomic():
            return RejectedImageCandidate.objects.create(
                image=image,
                image_ref=image.pk,
                product_ref=image.product_id,
                product_snapshot=_product_snapshot(image),
                file=saved_name,
                checksum=checksum,
                readable=True,
                render_key=render_key,
                processing_version=processing_version,
                qc_rules_version=qc_rules_version,
                mode=mode,
                reasons=reasons,
                reason_text=reason_text,
                source=source,
                actor=actor,
            )
    except IntegrityError:
        storage.delete(saved_name)
        return RejectedImageCandidate.objects.filter(
            image_ref=image.pk, render_key=render_key, checksum=checksum
        ).first()
