"""Phase 8 · ступень 1 — сид синтетической песочницы.

Создаёт ОДНУ категорию-маркер и 8 фиктивных товаров с явными маркерами
`PH8-SYN-*` в code_1c / article / name. Ни одно значение не пересекается
с реальным каталогом: префикс PH8-SYN зарезервирован только под эту ступень.

Запускать ТОЛЬКО против изолированной БД proff58_phase8.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.catalog.models import Category, Product, ProductStatus, StockStatus

MARKER = "PH8-SYN"

# 001..005 — попадают в batch; 006..008 — «свидетели» вне batch.
SPECS = [
    ("001", "ФИКТИВНЫЙ ТОВАР PH8-SYN-001 (не каталог) перфоратор-макет", "SYNTHBRAND-A"),
    ("002", "ФИКТИВНЫЙ ТОВАР PH8-SYN-002 (не каталог) шуруповёрт-макет", "SYNTHBRAND-A"),
    ("003", "ФИКТИВНЫЙ ТОВАР PH8-SYN-003 (не каталог) неопознаваемый макет", "SYNTHBRAND-B"),
    ("004", "ФИКТИВНЫЙ ТОВАР PH8-SYN-004 (не каталог) спорный макет", "SYNTHBRAND-B"),
    ("005", "ФИКТИВНЫЙ ТОВАР PH8-SYN-005 (не каталог) чужая идентичность", "SYNTHBRAND-C"),
    ("006", "ФИКТИВНЫЙ ТОВАР PH8-SYN-006 (не каталог) свидетель вне batch", "SYNTHBRAND-C"),
    ("007", "ФИКТИВНЫЙ ТОВАР PH8-SYN-007 (не каталог) свидетель вне batch", "SYNTHBRAND-C"),
    ("008", "ФИКТИВНЫЙ ТОВАР PH8-SYN-008 (не каталог) свидетель вне batch", "SYNTHBRAND-C"),
]


@transaction.atomic
def run() -> None:
    if Product.objects.exclude(code_1c__startswith=MARKER).exists():
        raise SystemExit("ОТКАЗ: в БД есть НЕсинтетические товары — это не песочница.")

    root = Category.objects.filter(slug="ph8-syn-sandbox").first()
    if root is None:
        root = Category.add_root(
            name="PH8-SYN SANDBOX (не каталог)",
            slug="ph8-syn-sandbox",
        )

    for idx, (num, name, brand) in enumerate(SPECS):
        Product.objects.update_or_create(
            code_1c=f"{MARKER}-{num}",
            defaults=dict(
                article=f"{MARKER}-ART-{num}",
                barcode=f"4600000{num}",
                original_name=f"{name} [1С-макет]",
                source_group="PH8-SYN GROUP (не каталог)",
                name=name,
                brand=brand,
                category=root,
                price=Decimal("1000.00") + idx,
                stock_quantity=Decimal("5.000"),
                available_quantity=Decimal("5.000"),
                stock_status=StockStatus.IN_STOCK,
                status=ProductStatus.IMPORTED,
                is_active=False,
            ),
        )

    rows = list(Product.objects.order_by("pk").values_list("pk", "code_1c", "name"))
    for pk, code, name in rows:
        print(f"{pk}\t{code}\t{name}")
    print(f"TOTAL={len(rows)}")


run()
