"""DRF-2635: модель Review убрана из состояния Django, таблица остаётся до 0004.

Двухфазное удаление: код этой версии про таблицу не знает, а сама таблица
(пустая — на проде 0 строк) удаляется следующей миграцией, когда в работе уже
не останется кода, который её читает.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_review_per_order")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Review")],
            database_operations=[],
        ),
    ]
