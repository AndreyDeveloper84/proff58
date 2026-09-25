"""T3: опубликованные контакты переезжают из кода витрины в SiteSettings.contacts.

Пустые ключи заполняются текущими значениями (те, что были зашиты в
frontend/lib/site.ts); заполненные не трогаются. Запись создаётся, если её нет.
"""

from django.db import migrations


def seed(apps, schema_editor):
    from apps.core.contacts import seed_defaults

    SiteSettings = apps.get_model("core", "SiteSettings")
    settings = SiteSettings.objects.order_by("pk").first()
    if settings is None:
        SiteSettings.objects.create(contacts=seed_defaults({}))
        return
    contacts = settings.contacts if isinstance(settings.contacts, dict) else {}
    seeded = seed_defaults(contacts)
    if seeded != contacts:
        settings.contacts = seeded
        settings.save(update_fields=["contacts"])


class Migration(migrations.Migration):
    dependencies = [("core", "0002_alter_sitesettings_requisites")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
