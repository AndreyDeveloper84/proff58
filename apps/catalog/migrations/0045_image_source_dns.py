# MEDIA-SOURCE-02: источник изображений dns-shop.ru.
# Только choices (state Django): колонка — varchar(16) без CHECK/enum, SQL не
# выполняется, существующие значения и данные не меняются.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0044_image_skipped_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productimage",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Загружено вручную"),
                    ("resanta", "resanta.ru"),
                    ("vihr", "vihr.su"),
                    ("interskol", "interskol.ru"),
                    ("zubr", "zubr.ru"),
                    ("huter", "huter.su"),
                    ("vseinstrumenti", "vseinstrumenti.ru"),
                    ("hanskonner", "hanskonner.ru"),
                    ("einhell", "einhell.de"),
                    ("thorvik", "thorvik.ru"),
                    ("dns", "dns-shop.ru"),
                ],
                db_index=True,
                default="manual",
                help_text="Откат прогона сбора удаляет только НЕ manual-записи.",
                max_length=16,
                verbose_name="Источник",
            ),
        ),
    ]
