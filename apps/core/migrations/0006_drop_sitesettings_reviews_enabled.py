"""DRF-2635, фаза 2: удалить колонку флага «Отзывы».

Поле ушло из состояния Django в 0005, код этой версии колонку не выбирает —
удаление не ломает работающий во время выката web.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0005_remove_sitesettings_reviews_enabled")]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE core_sitesettings DROP COLUMN IF EXISTS reviews_enabled",
            reverse_sql=(
                "ALTER TABLE core_sitesettings "
                "ADD COLUMN IF NOT EXISTS reviews_enabled boolean NOT NULL DEFAULT false"
            ),
        ),
    ]
