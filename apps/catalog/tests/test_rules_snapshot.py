"""Механизм snapshot-изоляции shadow-прогона (P1.6).

TransactionTestCase: доказывает, что REPEATABLE READ READ ONLY держит
стабильный снапшот пула при конкурентной вставке из второго соединения
(отдельный поток = отдельный thread-local connection). Полная команда здесь
не гоняется — тестируется сам механизм изоляции.
"""

import threading
import uuid

from django.db import connection, transaction
from django.test import TransactionTestCase

from apps.catalog.models import Product

SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"


def _product_payload(**kw):
    payload = dict(
        name="",
        slug=f"snap-{uuid.uuid4().hex[:8]}",
        original_name="Товар снапшот-теста",
        article=f"SNAP-{uuid.uuid4().hex[:6]}",
        source_group="Крепёж",
        is_active=True,
        content_locked=False,
        available_quantity=1,
        price="100",
    )
    payload.update(kw)
    return payload


class RepeatableReadSnapshotTest(TransactionTestCase):
    def test_repeatable_read_holds_snapshot(self):
        if connection.vendor != "postgresql":
            self.skipTest("REPEATABLE READ READ ONLY поддерживается только на PostgreSQL")

        Product.objects.create(**_product_payload())
        inserted = threading.Event()

        def writer():
            try:
                # поток получает своё (второе) соединение; autocommit → insert
                # коммитится сразу, пока основная транзакция открыта
                Product.objects.create(**_product_payload())
            finally:
                inserted.set()
                connection.close()

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(SNAPSHOT_SQL)
            count_before = Product.objects.count()
            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(inserted.wait(timeout=10), "writer-поток не завершил вставку")
            thread.join(timeout=10)
            count_after_insert = Product.objects.count()

        # снапшот стабилен: конкурентная вставка из второго соединения не видна
        self.assertEqual(count_after_insert, count_before)
        # после выхода из snapshot-транзакции вставленный товар виден
        self.assertEqual(Product.objects.count(), count_before + 1)
