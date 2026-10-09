import uuid

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_alter_user_phone_user_accounts_user_unique_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="inactivity_warning_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Предупреждение о неактивности",
            ),
        ),
        migrations.CreateModel(
            name="AccountDeletionAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("user_request", "Запрос пользователя"),
                            ("inactivity", "Длительная неактивность"),
                        ],
                        max_length=20,
                    ),
                ),
                ("result", models.CharField(default="success", max_length=20)),
                ("procedure_version", models.CharField(default="v1", max_length=20)),
            ],
            options={
                "verbose_name": "Аудит обезличивания аккаунта",
                "verbose_name_plural": "Аудит обезличивания аккаунтов",
            },
        ),
    ]
