"""Начальная миграция: DeliveryZone и PickupPoint."""

import decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DeliveryZone",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "name",
                    models.CharField(max_length=200, verbose_name="Название зоны"),
                ),
                (
                    "slug",
                    models.SlugField(max_length=100, unique=True, verbose_name="Слаг"),
                ),
                (
                    "delivery_type",
                    models.CharField(
                        choices=[
                            ("courier", "Курьерская доставка"),
                            ("pickup", "Самовывоз"),
                        ],
                        default="courier",
                        max_length=20,
                        verbose_name="Способ доставки",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(decimal.Decimal("0.00"))
                        ],
                        verbose_name="Стоимость доставки",
                    ),
                ),
                (
                    "free_from",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Сумма заказа, начиная с которой доставка бесплатна. Пусто = нет порога.",
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(decimal.Decimal("0.01"))
                        ],
                        verbose_name="Бесплатно от суммы",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Активна"),
                ),
            ],
            options={
                "verbose_name": "Зона доставки",
                "verbose_name_plural": "Зоны доставки",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="PickupPoint",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "name",
                    models.CharField(max_length=200, verbose_name="Название"),
                ),
                (
                    "address",
                    models.CharField(max_length=500, verbose_name="Адрес"),
                ),
                (
                    "working_hours",
                    models.CharField(
                        help_text="Например: Пн-Пт 9:00-18:00, Сб 10:00-15:00",
                        max_length=200,
                        verbose_name="Часы работы",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Активен"),
                ),
            ],
            options={
                "verbose_name": "Пункт самовывоза",
                "verbose_name_plural": "Пункты самовывоза",
                "ordering": ["name"],
            },
        ),
    ]
