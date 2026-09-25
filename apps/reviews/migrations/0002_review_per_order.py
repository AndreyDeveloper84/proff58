# Полная замена схемы отзывов (#573): generic-модель (#72, subject_type/subject_id,
# одна оценка) → отзыв на заказ (OneToOne, три оценки, причина отклонения).
# Таблица 0001 пуста в любом окружении: флаг reviews всегда был default off,
# API у старой схемы не существовало — DeleteModel безопасен.
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0001_initial"),
        ("orders", "0011_order_delivery_slot_order_delivery_slot_snapshot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name="Review"),
        migrations.CreateModel(
            name="Review",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review",
                        to="orders.order",
                        verbose_name="Заказ",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviews",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
                (
                    "author_name",
                    models.CharField(
                        blank=True,
                        help_text="Снапшот («Имя И.»): публичный API отдаёт только его, не ПДн автора.",
                        max_length=150,
                        verbose_name="Публичное имя",
                    ),
                ),
                (
                    "product_rating",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                        verbose_name="Оценка товаров",
                    ),
                ),
                (
                    "delivery_rating",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                        verbose_name="Оценка доставки",
                    ),
                ),
                (
                    "shop_rating",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                        verbose_name="Оценка магазина",
                    ),
                ),
                ("text", models.TextField(blank=True, verbose_name="Текст")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "На модерации"),
                            ("approved", "Опубликован"),
                            ("rejected", "Отклонён"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=10,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "rejection_reason",
                    models.TextField(blank=True, verbose_name="Причина отклонения"),
                ),
                (
                    "moderated_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Промодерирован"),
                ),
            ],
            options={
                "verbose_name": "Отзыв",
                "verbose_name_plural": "Отзывы",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "-created_at"], name="reviews_status_created_idx"
                    )
                ],
            },
        ),
    ]
