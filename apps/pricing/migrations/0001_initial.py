import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Перенос владения моделью PriceRecord из sync_1c в pricing.

    Только состояние (state_operations): таблица ``sync_1c_pricerecord`` уже
    существует физически (создана sync_1c.0001 + constraint в sync_1c.0003),
    поэтому database_operations пуст — DDL не выполняется, данные не двигаются.
    """

    initial = True

    dependencies = [
        # FK на Product — нужна таблица catalog.Product.
        ("catalog", "0001_initial"),
        # Таблица и constraint PriceRecord уже созданы к этому моменту в sync_1c.
        ("sync_1c", "0003_nomenclaturestaging_row_hash_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="PriceRecord",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "code_1c",
                            models.CharField(db_index=True, max_length=50, verbose_name="Код 1С"),
                        ),
                        (
                            "price_type",
                            models.CharField(
                                default="retail",
                                help_text="retail / wholesale / promo или код типа цены из 1С.",
                                max_length=50,
                                verbose_name="Тип цены",
                            ),
                        ),
                        (
                            "value",
                            models.DecimalField(
                                decimal_places=2, max_digits=14, verbose_name="Цена"
                            ),
                        ),
                        (
                            "currency",
                            models.CharField(default="RUB", max_length=3, verbose_name="Валюта"),
                        ),
                        (
                            "is_current",
                            models.BooleanField(
                                db_index=True, default=True, verbose_name="Актуальная"
                            ),
                        ),
                        (
                            "valid_from",
                            models.DateTimeField(auto_now_add=True, verbose_name="Действует с"),
                        ),
                        (
                            "product",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="price_records",
                                to="catalog.product",
                                verbose_name="Товар",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Цена из 1С",
                        "verbose_name_plural": "Цены из 1С",
                        "db_table": "sync_1c_pricerecord",
                        "ordering": ["-valid_from"],
                        "indexes": [
                            models.Index(
                                fields=["code_1c", "price_type", "is_current"],
                                name="sync_1c_pri_code_1c_5afecb_idx",
                            )
                        ],
                    },
                ),
                migrations.AddConstraint(
                    model_name="pricerecord",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("is_current", True)),
                        fields=("code_1c", "price_type", "currency"),
                        name="uniq_current_price_per_code_type_currency",
                    ),
                ),
            ],
        ),
    ]
