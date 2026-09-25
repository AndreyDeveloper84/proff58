"""DEVIATION-2: re-slug option id=16 + уникальность (attribute, slug) для непустых slug.

Порядок операций важен: сначала data re-slug (устраняет единственный дубль),
затем констрейнт. Guard: свежая БД без id=16 — no-op; сначала проверяется
идентичность id=16 (value + атрибут tool_type) и только потом NEW_SLUG считается
идемпотентным состоянием; перед re-slug проверяется каноническая запись id=73;
любое неожиданное состояние — RuntimeError (остановка до ручной проверки).
"""

from django.db import migrations, models
from django.db.models import Q

OPTION_ID = 16
EXPECTED_VALUE = "Степлеры и заклёпочники"
CANONICAL_OPTION_ID = 73
CANONICAL_VALUE = "Степлеры (скобозабивные)"
TOOL_TYPE_ATTRIBUTE_SLUG = "tool_type"
OLD_SLUG = "steplery"
NEW_SLUG = "steplery-i-zaklepochniki"


def reslug_forward(apps, schema_editor):
    AttributeOption = apps.get_model("catalog", "AttributeOption")
    try:
        opt = AttributeOption.objects.get(pk=OPTION_ID)
    except AttributeOption.DoesNotExist:
        return  # свежая БД без исторических данных — нечего мигрировать
    # Сначала идентичность записи: трогать разрешено только известную историческую запись.
    if opt.value != EXPECTED_VALUE or opt.attribute.slug != TOOL_TYPE_ATTRIBUTE_SLUG:
        raise RuntimeError(
            f"DEVIATION-2 reslug guard: option {OPTION_ID} имеет неожиданные "
            f"value/attribute: {opt.value!r}/{opt.attribute.slug!r}; ожидались "
            f"{EXPECTED_VALUE!r}/{TOOL_TYPE_ATTRIBUTE_SLUG!r}. Миграция остановлена."
        )
    if opt.slug == NEW_SLUG:
        return  # уже применено (идемпотентность)
    if opt.slug != OLD_SLUG:
        raise RuntimeError(
            f"DEVIATION-2 reslug guard: option {OPTION_ID} имеет неожиданный slug "
            f"{opt.slug!r}; ожидался {OLD_SLUG!r}. Миграция остановлена."
        )
    # Перед re-slug каноническая запись id=73 обязана существовать и сохранять steplery,
    # иначе после переименования id=16 в каталоге не останется канонического steplery.
    canonical = AttributeOption.objects.filter(pk=CANONICAL_OPTION_ID).first()
    if (
        canonical is None
        or canonical.value != CANONICAL_VALUE
        or canonical.slug != OLD_SLUG
        or canonical.attribute.slug != TOOL_TYPE_ATTRIBUTE_SLUG
    ):
        state = (
            f"{canonical.value!r}/{canonical.slug!r}/{canonical.attribute.slug!r}"
            if canonical is not None
            else "запись отсутствует"
        )
        raise RuntimeError(
            f"DEVIATION-2 reslug guard: каноническая option {CANONICAL_OPTION_ID} в "
            f"неожиданном состоянии: {state}; ожидались "
            f"{CANONICAL_VALUE!r}/{OLD_SLUG!r}/{TOOL_TYPE_ATTRIBUTE_SLUG!r}. "
            f"Миграция остановлена."
        )
    if AttributeOption.objects.filter(attribute_id=opt.attribute_id, slug=NEW_SLUG).exists():
        raise RuntimeError(f"DEVIATION-2 reslug guard: slug {NEW_SLUG!r} уже занят.")
    opt.slug = NEW_SLUG
    opt.save(update_fields=["slug"])


def reslug_backward(apps, schema_editor):
    AttributeOption = apps.get_model("catalog", "AttributeOption")
    AttributeOption.objects.filter(pk=OPTION_ID, slug=NEW_SLUG).update(slug=OLD_SLUG)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0026_catalogchange_applied_by_catalogchange_comment_and_more"),
    ]

    operations = [
        migrations.RunPython(reslug_forward, reslug_backward),
        migrations.AddConstraint(
            model_name="attributeoption",
            constraint=models.UniqueConstraint(
                fields=["attribute", "slug"],
                condition=~Q(slug=""),
                name="uniq_attributeoption_attr_slug_nonempty",
            ),
        ),
    ]
