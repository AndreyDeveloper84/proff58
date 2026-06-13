import pytest

from apps.sync_1c.models import (
    NomenclatureStaging,
    PriceRecord,
    StagingStatus,
    StockRecord,
    SyncLog,
)


@pytest.mark.django_db
def test_staging_created_with_raw_payload():
    record = NomenclatureStaging.objects.create(
        code_1c="000001234",
        article="GSB13-RE",
        raw_payload={"name": "ДРЕЛЬ GSB 13 RE", "price": "4500.00", "qty": "10"},
        name_1c="ДРЕЛЬ GSB 13 RE",
        price=4500.00,
        stock=10,
    )
    assert record.status == StagingStatus.PENDING
    assert record.product is None
    assert record.raw_payload["qty"] == "10"


@pytest.mark.django_db
def test_price_record():
    p = PriceRecord.objects.create(code_1c="000001234", value=4500, price_type="retail")
    assert p.is_current is True
    assert str(p.currency) == "RUB"


@pytest.mark.django_db
def test_stock_record_unique_per_warehouse():
    StockRecord.objects.create(code_1c="000001234", warehouse="main", quantity=10)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        StockRecord.objects.create(code_1c="000001234", warehouse="main", quantity=5)


@pytest.mark.django_db
def test_sync_log():
    log = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.PRICES,
        result=SyncLog.SyncResult.OK,
        rows_total=100,
        rows_ok=100,
    )
    assert "Цены" in str(log)
