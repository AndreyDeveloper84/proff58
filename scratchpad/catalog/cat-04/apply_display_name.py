# -*- coding: utf-8 -*-
"""CAT-04 · задача 1: display_name для size в izmeritelnyy-ugolniki-i-lineyki (staging).

Dry-run по умолчанию; запись — только с CAT04_WRITE=1, одной транзакцией.
Fail-closed: строка должна существовать ровно одна, category/attribute — те самые.
"""
import os

from django.db import transaction

from apps.catalog.models import CategoryAttribute

TARGET = "Размер"

qs = CategoryAttribute.objects.filter(
    category__slug="izmeritelnyy-ugolniki-i-lineyki", attribute__slug="size"
)
rows = list(qs)
assert len(rows) == 1, f"ожидалась ровно 1 строка CA, найдено {len(rows)}"
ca = rows[0]
print("row id:", ca.pk, "display_name:", repr(ca.display_name), "->", repr(TARGET))

if os.environ.get("CAT04_WRITE") != "1":
    print("DRY-RUN: записи нет (CAT04_WRITE!=1)")
else:
    assert ca.display_name == "", f"display_name уже задан: {ca.display_name!r} — стоп"
    with transaction.atomic():
        ca.display_name = TARGET
        ca.save(update_fields=["display_name"])
    ca.refresh_from_db()
    print("WROTE ok:", repr(ca.display_name))
