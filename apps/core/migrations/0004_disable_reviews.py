"""T4 (решение владельца 24.09.2026): раздел отзывов отключён. Данные и админка
остаются; включить обратно — флагом «Отзывы» в настройках сайта."""

from django.db import migrations


def disable(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(reviews_enabled=True).update(reviews_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("core", "0003_seed_site_contacts")]
    operations = [migrations.RunPython(disable, migrations.RunPython.noop)]
