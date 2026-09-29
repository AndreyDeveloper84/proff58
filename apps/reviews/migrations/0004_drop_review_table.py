"""DRF-2635, фаза 2: удалить пустую таблицу отзывов.

Модель Review ушла из состояния Django в 0003 и в коде этой версии не
используется, поэтому таблица удаляется без окна сбоя на выкате. На проде в ней
было 0 строк (проверено 29.09.2026). Обратная миграция таблицу не восстанавливает:
раздел отзывов убран, возвращать его — отдельная задача.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("reviews", "0003_remove_review_state")]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS reviews_review",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
