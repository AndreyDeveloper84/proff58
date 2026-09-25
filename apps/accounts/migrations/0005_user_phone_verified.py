from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_profile_b2b_verified_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_verified",
            field=models.BooleanField(default=False, verbose_name="Телефон подтверждён"),
        ),
    ]
