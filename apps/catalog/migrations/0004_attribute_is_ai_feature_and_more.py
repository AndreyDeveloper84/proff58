# Provenance characteristik (EAV) — Фаза B #96.

import django.core.validators
from django.db import migrations, models


def set_existing_source_manual(apps, schema_editor):
    """Существующие значения характеристик помечаем как ручные.

    manual — высший приоритет, поэтому enrich_attributes их не перезапишет
    автоматически (защита ранее внесённых вручную данных).
    """
    ProductAttributeValue = apps.get_model("catalog", "ProductAttributeValue")
    ProductAttributeValue.objects.update(source="manual")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_importrun_attributeoption_slug_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="attribute",
            name="is_ai_feature",
            field=models.BooleanField(
                default=False,
                help_text="Плохо извлекается regex/словарём из названия — кандидат на добор LLM (#62).",
                verbose_name="AI-характеристика",
            ),
        ),
        migrations.AddField(
            model_name="productattributevalue",
            name="confidence",
            field=models.SmallIntegerField(
                default=100,
                help_text="0–100. Только аналитика/AI, в решении о перезаписи НЕ участвует (перезапись решает source).",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Уверенность",
            ),
        ),
        migrations.AddField(
            model_name="productattributevalue",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Вручную"),
                    ("import_1c", "Импорт 1С"),
                    ("regex", "Regex по названию"),
                    ("keyword", "Ключевое слово"),
                    ("llm", "AI/LLM"),
                ],
                default="manual",
                help_text="Приоритет перезаписи берётся из source_priority в attribute_rules.json: manual не затирается regex/keyword.",
                max_length=12,
                verbose_name="Источник",
            ),
        ),
        migrations.RunPython(set_existing_source_manual, migrations.RunPython.noop),
    ]
