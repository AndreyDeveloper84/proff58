# ХАР-03B (Часть C): узел «Ручной инструмент» дублируется — легаси slug=ruchnoy-instrument
# (is_active=False, on_site=False, is_site_v2=False, 0 собственных товаров) и живой v2-узел
# slug=ruchnoy делят одно имя на depth=1. load_attributes._bind_category берёт первый по pk
# depth=1-узел без учёта активности — легаси-узел (меньший pk) выигрывает, и 10 tool_type-блоков
# (klyuchi-gaechnye, otvertki, nabory-otvertok, golovki, vorotki, molotki, passatizhi, bokorezy,
# domkraty, nozhovki) садят фасеты не на витрину. Легаси-узел не убирается (его поддерево из
# 21 категории и 1316 товаров ещё используется 1С-обменом), поэтому решение — снять коллизию
# имени переименованием, а не удалением.

from django.db import migrations

LEGACY_SLUG = "ruchnoy-instrument"
OLD_NAME = "Ручной инструмент"
NEW_NAME = "Ручной инструмент (легаси)"


def rename_forward(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Category.objects.filter(
        slug=LEGACY_SLUG,
        name=OLD_NAME,
        is_active=False,
        on_site=False,
        is_site_v2=False,
    ).update(name=NEW_NAME)


def rename_backward(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Category.objects.filter(slug=LEGACY_SLUG, name=NEW_NAME).update(name=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0034_merge_gitlab_20260805"),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_backward),
    ]
