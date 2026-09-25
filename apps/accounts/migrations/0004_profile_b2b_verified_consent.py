from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_wishlistitem")]
    operations = [
        migrations.AddField(
            "profile",
            "is_b2b_verified",
            models.BooleanField(default=False, verbose_name="B2B верифицирован"),
        ),
        migrations.AddField(
            "profile",
            "pd_consent_at",
            models.DateTimeField(null=True, blank=True, verbose_name="Согласие ПДн"),
        ),
        migrations.AddField(
            "profile",
            "pd_consent_version",
            models.CharField(max_length=32, blank=True, verbose_name="Версия политики ПДн"),
        ),
    ]
