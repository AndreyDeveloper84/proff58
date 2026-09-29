"""DRF-2635: модель Review убрана из состояния Django, таблица остаётся до 0004.

Двухфазное удаление: код этой версии про таблицу не знает, а сама таблица
(пустая — на проде 0 строк) удаляется следующей миграцией, когда в работе уже
не останется кода, который её читает.

Внешние ключи таблицы (на заказы и пользователей) снимаются уже здесь: Django
больше не знает о таблице, и её ключи мешали бы TRUNCATE заказов и
пользователей (flush в тестах) — PostgreSQL не очищает таблицу, на которую
ссылается чужой внешний ключ, даже пустую.
"""

from django.db import migrations

DROP_FOREIGN_KEYS = """
DO $$
DECLARE r record;
BEGIN
    IF to_regclass('reviews_review') IS NULL THEN
        RETURN;
    END IF;
    FOR r IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'reviews_review'::regclass AND contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE reviews_review DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_review_per_order")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Review")],
            database_operations=[
                migrations.RunSQL(sql=DROP_FOREIGN_KEYS, reverse_sql=migrations.RunSQL.noop),
            ],
        ),
    ]
