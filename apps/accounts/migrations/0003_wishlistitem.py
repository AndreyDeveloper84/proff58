import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_max_chat_id"),
        ("catalog", "0022_moderationproduct"),
    ]
    operations = [
        migrations.CreateModel(
            name="WishlistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wishlist",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Избранное",
                "verbose_name_plural": "Избранное",
                "unique_together": {("user", "product")},
            },
        ),
    ]
