from django.db import migrations


class Migration(migrations.Migration):
    """Убрать PriceRecord из state приложения sync_1c.

    Модель перенесена во владение pricing (pricing.0001_initial создал её в
    своём state). Здесь — только удаление из state sync_1c: таблица
    ``sync_1c_pricerecord`` физически НЕ удаляется (database_operations пуст).
    После этой миграции модель PriceRecord присутствует в state ровно у одного
    приложения — pricing.
    """

    dependencies = [
        ("pricing", "0001_initial"),
        ("sync_1c", "0005_synclog_counters_alter_synclog_result"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="PriceRecord"),
            ],
        ),
    ]
