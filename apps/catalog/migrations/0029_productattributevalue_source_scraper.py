# PARS-04: источник `scraper` (парсер сайтов производителей) для PAV.
# Неразрушающая: choices — ограничение уровня Python, схема БД не меняется.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0028_categoryattribute_display_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productattributevalue",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Вручную"),
                    ("import_1c", "Импорт 1С"),
                    ("regex", "Regex по названию"),
                    ("keyword", "Ключевое слово"),
                    ("rules", "Правила каталога"),
                    ("llm", "AI/LLM"),
                    ("inferred", "Инференс по атрибутам"),
                    ("web", "Web-поиск"),
                    ("marketplace", "Маркетплейс"),
                    ("scraper", "Парсер сайтов производителей"),
                ],
                default="manual",
                help_text="Приоритет перезаписи берётся из source_priority в attribute_rules.json: manual не затирается regex/keyword.",
                max_length=12,
                verbose_name="Источник",
            ),
        ),
    ]
