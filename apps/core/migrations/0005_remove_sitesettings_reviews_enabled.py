"""DRF-2635: флаг «Отзывы» убран вместе с разделом отзывов.

Поле удаляется из состояния Django, а колонка в базе пока остаётся — с
DB-значением по умолчанию ``false``: код этой версии её не пишет, и вставка
настроек (``get_solo()`` → ``get_or_create``) не падает на NOT NULL. Саму
колонку удаляет следующая миграция, когда старого кода, выбирающего её, уже не
будет: иначе во время ``migrate`` работающий старый web ловил бы ошибку на
каждом чтении настроек — а они читаются в корзине и оформлении заказа.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0004_disable_reviews")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="sitesettings", name="reviews_enabled"),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE core_sitesettings ALTER COLUMN reviews_enabled SET DEFAULT false",
                    reverse_sql="ALTER TABLE core_sitesettings ALTER COLUMN reviews_enabled DROP DEFAULT",
                ),
            ],
        ),
    ]
