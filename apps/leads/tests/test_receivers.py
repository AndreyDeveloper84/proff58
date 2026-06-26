import logging

import pytest

from apps.leads.receivers import notify_new_inquiry


@pytest.mark.django_db
def test_notify_logs_inquiry(product, caplog):
    with caplog.at_level(logging.INFO, logger="apps.leads"):
        notify_new_inquiry(
            sender=None, inquiry_id=1, kind="price_request", product_id=product.pk
        )
    assert any("price_request" in r.getMessage() for r in caplog.records)
