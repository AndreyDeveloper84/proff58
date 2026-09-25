"""Данные: развести принятую копию и кандидата на уже существующих записях.

До этой миграции `display` был и принятой копией, и черновиком одновременно;
витрина (`storefront_image`) показывала его только при `processing_status=done`.
Разводим поле, не трогая то, что уже видит покупатель:

- `done` + `display` — уже принятая копия, остаётся в `display` как была;
- любой другой статус с непустым `display` (`needs_review`/`queued`/`failed`/…) —
  это был черновик, который витрина и так не показывала: переносим ссылку на файл в
  `candidate`, из `display` убираем. Сам файл на диске не двигаем и не удаляем —
  меняется только то, на какое поле записи он привязан.
- `done`/`rejected` — решение принято ДО контролёра качества: помечаем
  `qc_source="legacy"`, чтобы калибровка новых правил не считала эти записи
  проверенной вручную или автоматикой контролёра разметкой (§5.4 задания).

Обратная миграция — лучшее приближение, а не гарантия: она возвращает `candidate`
обратно в `display` только для статусов, которые существовали до этой миграции.
Новые статусы (`observed`, `candidate_rejected`) и любые кандидаты, появившиеся уже
после применения этой миграции в обычной работе, откатом не разбираются — это
ожидаемо для отката вперёд идущей схемы, а не инструмент отмены боевой обработки.
"""

from django.db import migrations

#: Статусы, которые уже существовали до этой доработки — только для них обратная
#: миграция имеет смысл (см. докстринг модуля).
_LEGACY_STATUSES = (
    "none",
    "queued",
    "needs_rembg",
    "needs_review",
    "done",
    "skipped",
    "rejected",
    "failed",
)


def move_pending_display_to_candidate(apps, schema_editor):
    ProductImage = apps.get_model("catalog", "ProductImage")
    pending = ProductImage.objects.exclude(processing_status="done").exclude(display="")
    for image in pending.iterator():
        image.candidate = image.display.name
        image.candidate_checksum = image.display_checksum
        image.candidate_mode = image.processing_mode
        image.candidate_created_at = image.processed_at
        image.display = ""
        image.display_checksum = ""
        image.save(
            update_fields=[
                "candidate",
                "candidate_checksum",
                "candidate_mode",
                "candidate_created_at",
                "display",
                "display_checksum",
            ]
        )

    ProductImage.objects.filter(processing_status__in=("done", "rejected")).update(
        qc_source="legacy"
    )


def reverse_move(apps, schema_editor):
    ProductImage = apps.get_model("catalog", "ProductImage")
    pending = ProductImage.objects.filter(processing_status__in=_LEGACY_STATUSES).exclude(
        candidate=""
    )
    for image in pending.iterator():
        image.display = image.candidate.name
        image.display_checksum = image.candidate_checksum
        image.candidate = ""
        image.candidate_checksum = ""
        image.candidate_mode = ""
        image.candidate_created_at = None
        image.save(
            update_fields=[
                "display",
                "display_checksum",
                "candidate",
                "candidate_checksum",
                "candidate_mode",
                "candidate_created_at",
            ]
        )
    ProductImage.objects.filter(qc_source="legacy").update(qc_source="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0047_productimageevent_rejectedimagecandidate_and_more"),
    ]

    operations = [
        migrations.RunPython(move_pending_display_to_candidate, reverse_move),
    ]
