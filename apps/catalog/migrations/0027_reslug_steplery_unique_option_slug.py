"""DEVIATION-2: re-slug option id=16 + уникальность (attribute, slug) для непустых slug.

Порядок операций важен: сначала data re-slug (устраняет единственный дубль),
затем констрейнт. Guard: свежая БД без id=16 — no-op; уже re-slugged — no-op;
неожиданное состояние id=16 — RuntimeError (остановка до ручной проверки).
"""

from django.db import migrations, models
from django.db.models import Q

OPTION_ID = 16
EXPECTED_VALUE = "Степлеры и заклёпочники"
OLD_SLUG = "steplery"
NEW_SLUG = "steplery-i-zaklepochniki"


def reslug_forward(apps, schema_editor):
    AttributeOption = apps.get_model("catalog", "AttributeOption")
    try:
        opt = AttributeOption.objects.get(pk=OPTION_ID)
    except AttributeOption.DoesNotExist:
        return  # свежая БД без исторических данных — нечего мигрировать
    if opt.slug == NEW_SLUG:
        return  # уже применено (идемпотентность)
    if opt.value != EXPECTED_VALUE or opt.slug != OLD_SLUG:
        raise RuntimeError(
            f"DEVIATION-2 reslug guard: option {OPTION_ID} имеет неожиданные "
            f"value/slug: {opt.value!r}/{opt.slug!r}; ожидались "
            f"{EXPECTED_VALUE!r}/{OLD_SLUG!r}. Миграция остановлена."
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
