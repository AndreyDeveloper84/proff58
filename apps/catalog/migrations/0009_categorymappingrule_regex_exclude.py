from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_alter_productattributevalue_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="categorymappingrule",
            name="exclude_pattern",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Негативный guard: если выражение найдено в названии — правило "
                    "НЕ срабатывает (напр. «бур», но исключить «бурения земл|мотобур»)."
                ),
                max_length=255,
                verbose_name="Исключение (regex по имени)",
            ),
        ),
        migrations.AlterField(
            model_name="categorymappingrule",
            name="rule_type",
            field=models.CharField(
                choices=[
                    ("article", "По артикулу (точное совпадение)"),
                    ("name_contains", "По слову в названии"),
                    ("regex", "По регулярному выражению (имя)"),
                    ("brand_prefix", "По бренду + серии модели"),
                    ("source_group", "По исходной группе 1С"),
                ],
                max_length=20,
                verbose_name="Тип правила",
            ),
        ),
    ]
