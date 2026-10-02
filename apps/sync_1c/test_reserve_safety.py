"""DRF-2737: обмен с 1С не затирает резерв сайта и контент устаревшим снимком товара.

Обмен читает товары батча один раз, а пишет построчно — между чтением и записью
конкретной строки успевают пройти чекаут и правки менеджера в админке. Каждый тест
воспроизводит именно это окно: «чужая» запись в БД делается ПОСЛЕ того, как обмен
загрузил товары, и ДО того, как он записал строку.

Раньше обмен сохранял весь устаревший инстанс (полный ``save()`` / ``bulk_update`` со
счётчиками остатка): удержание покупателя исчезало, товар продавался второй раз, а
название и статус откатывались к прочитанным в начале батча.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest

from apps.catalog.models import Product, ProductStatus
from apps.sync_1c import bulk_import, matching, normalizers, pricing, stock, use_cases

pytestmark = pytest.mark.django_db

CODE = "1c-900"


@pytest.fixture
def product():
    return Product.objects.create(
        name="Перфоратор",
        code_1c=CODE,
        slug="perf-900",
        price=Decimal("1000.00"),
        status=ProductStatus.DRAFT,
        stock_quantity=Decimal("5"),
        available_quantity=Decimal("5"),
        reserved_quantity=Decimal("0"),
    )


@pytest.fixture
def cart_with_product(db):
    """Корзина гостя с двумя штуками опубликованного товара (остаток 5)."""
    from apps.orders.models import Cart
    from apps.orders.services import add_to_cart

    product = Product.objects.create(
        name="Шуруповёрт",
        code_1c="1c-950",
        slug="shurupovert-950",
        unit="шт",
        price=Decimal("3000.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=Decimal("5"),
        available_quantity=Decimal("5"),
    )
    cart = Cart.objects.create(session_key="b3-session")
    add_to_cart(cart, product, 2)
    return cart, product


def _checkout_and_edit(pk: int) -> None:
    """Что успело случиться, пока шёл батч: покупатель удержал 2 штуки, менеджер
    переименовал товар и опубликовал его."""
    Product.objects.filter(pk=pk).update(
        available_quantity=Decimal("3"),
        reserved_quantity=Decimal("2"),
        name="Перфоратор ЗУБР ЗПМ-50",
        status=ProductStatus.PUBLISHED,
    )


def _once(action):
    """Обёртка-побочный эффект: выполнить ``action`` при первом вызове."""
    state = {"done": False}

    def run():
        if not state["done"]:
            state["done"] = True
            action()

    return run


def _racing_match(pk: int):
    """Матчинг строки, перед которым «другая сессия» изменила товар. Карты батча к
    этому моменту уже построены — это и есть окно между чтением и записью."""
    race = _once(lambda: _checkout_and_edit(pk))
    real = matching.resolve_in_memory

    def racing(item, maps):
        race()
        return real(item, maps)

    return mock.patch.object(matching, "resolve_in_memory", side_effect=racing)


# Колонки, которые обмен не имеет права писать: счётчик резерва сайта и контент.
_FOREIGN_COLUMNS = ('"reserved_quantity"', '"name"', '"category_id"', '"status"', '"slug"')


def _assert_locked_before_update_and_own_columns_only(queries) -> None:
    """Запись товара: замок строки взят раньше UPDATE, в SET — только поля 1С."""
    sqls = [q["sql"] for q in queries if '"catalog_product"' in q["sql"]]
    locks = [i for i, sql in enumerate(sqls) if "FOR NO KEY UPDATE" in sql]
    assert locks, "обмен пишет остаток, не взяв замок строки товара"
    lock_at = locks[0]
    updates = [(i, sql) for i, sql in enumerate(sqls) if sql.startswith("UPDATE")]
    assert updates, "обмен ничего не записал"
    for i, sql in updates:
        assert i > lock_at, "UPDATE товара раньше замка строки"
        set_clause = sql.split(" WHERE ")[0]
        for column in _FOREIGN_COLUMNS:
            assert column not in set_clause, f"обмен пишет чужую колонку {column}"


def _assert_site_state_survived(product: Product) -> None:
    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2"), "удержание покупателя потеряно"
    assert product.name == "Перфоратор ЗУБР ЗПМ-50", "название откатилось"
    assert product.status == ProductStatus.PUBLISHED, "статус откатился"


# ═══════════ prices/update — живой путь: батчи идут каждые несколько минут ═══════════


def test_price_update_keeps_reservation_and_content(product):
    with _racing_match(product.pk):
        _log, result = use_cases.update_prices([{"external_id": CODE, "price": "1200"}])

    assert result.updated == 1
    _assert_site_state_survived(product)
    assert product.price == Decimal("1200")
    assert product.available_quantity == Decimal("3")  # цены остаток не трогают вовсе


def test_price_update_writes_only_price_fields(product):
    """Страховка от возврата к полному save(): обмен ценами пишет только свои поля.
    Зачёркнутая цена — только если 1С её прислала: иначе в БД вернулось бы значение
    из инстанса, прочитанного в начале батча."""
    with mock.patch.object(Product, "save", autospec=True, side_effect=Product.save) as save:
        use_cases.update_prices([{"external_id": CODE, "price": "1200"}])
        use_cases.update_prices([{"external_id": CODE, "price": "1300", "old_price": "1500"}])

    first, second = save.call_args_list
    assert set(first.kwargs["update_fields"]) == {
        "price",
        "currency",
        "price_updated_at",
        "updated_at",
    }
    assert set(second.kwargs["update_fields"]) == {*pricing._PRICE_FIELDS, "updated_at"}


def test_price_update_takes_no_row_lock(product):
    """Ценам замок товара не нужен — и на каждой из тысяч строк прайса его быть не
    должно (большинство строк — «цена не изменилась»)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    use_cases.update_prices([{"external_id": CODE, "price": "1200"}])  # цена записана

    with CaptureQueriesContext(connection) as queries:
        _log, result = use_cases.update_prices([{"external_id": CODE, "price": "1200"}])

    assert result.skipped == 1  # та же цена — строка пропущена
    assert not [q for q in queries if "catalog_product" in q["sql"] and "FOR " in q["sql"]]


# ═══════════ stocks/update ═══════════


def test_stock_update_counts_available_from_fresh_reservation(product):
    with _racing_match(product.pk):
        _log, result = use_cases.update_stocks([{"external_id": CODE, "stock": "10"}])

    assert result.updated == 1
    _assert_site_state_survived(product)
    assert product.stock_quantity == Decimal("10")
    assert product.available_quantity == Decimal("8")  # 10 физически − 2 удержано сайтом


def test_stock_update_never_writes_site_reservation(product):
    """``reserved`` из 1С — её собственный резерв: счётчик сайта он не заменяет, но из
    свободного остатка вычитается вместе с резервом сайта."""
    Product.objects.filter(pk=product.pk).update(
        reserved_quantity=Decimal("2"), available_quantity=Decimal("3")
    )

    use_cases.update_stocks([{"external_id": CODE, "stock": "10", "reserved": "1"}])

    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == Decimal("7")  # 10 − 1 (1С) − 2 (сайт)


def test_explicit_available_from_1c_still_respects_site_reservation(product):
    """1С прислала готовое «доступно». О заказе, оформленном секунду назад, она ещё не
    знает — удержание сайта вычитается и здесь. Раньше число писалось как есть:
    удержанный товар возвращался в продажу, а отмена заказа добавляла его ещё раз."""
    with _racing_match(product.pk):
        use_cases.update_stocks([{"external_id": CODE, "stock": "10", "available_stock": "6"}])

    _assert_site_state_survived(product)
    assert product.available_quantity == Decimal("4")  # 6 по данным 1С − 2 удержано сайтом


def test_negative_reserved_from_1c_does_not_inflate_available(product):
    use_cases.update_stocks([{"external_id": CODE, "stock": "10", "reserved": "-3"}])

    product.refresh_from_db()
    assert product.available_quantity == Decimal("10")  # не 13


def test_row_with_only_reserved_changes_nothing(product):
    """Резерв 1С сайт не хранит — без ``stock`` в той же строке записывать нечего.
    Раньше такая строка затирала счётчик резерва сайта."""
    Product.objects.filter(pk=product.pk).update(reserved_quantity=Decimal("2"))
    before = Product.objects.get(pk=product.pk)

    _log, result = use_cases.update_stocks([{"external_id": CODE, "reserved": "4"}])

    assert (result.updated, result.skipped) == (0, 1)
    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == before.available_quantity
    assert product.stock_updated_at == before.stock_updated_at


def test_stock_event_is_computed_from_fresh_available(django_capture_on_commit_callbacks):
    """«Товар появился» решается по свежему остатку, а не по прочитанному в начале
    батча: ложный переход сжёг бы одноразовые подписки «сообщить о поступлении»."""
    from apps.core import events

    product = Product.objects.create(
        name="Дрель", code_1c="1c-901", slug="drel-901", available_quantity=Decimal("0")
    )
    seen = []

    def on_available(sender, **kwargs):
        seen.append((kwargs["old_available"], kwargs["new_available"]))

    events.product_stock_became_available.connect(on_available, dispatch_uid="b3-test")
    try:
        # Пока шёл батч, товар уже появился (другой поток): перехода 0→N для нас нет.
        real = matching.resolve_in_memory

        def racing(item, maps):
            Product.objects.filter(pk=product.pk).update(available_quantity=Decimal("4"))
            return real(item, maps)

        with (
            mock.patch.object(matching, "resolve_in_memory", side_effect=racing),
            django_capture_on_commit_callbacks(execute=True),
        ):
            use_cases.update_stocks([{"external_id": "1c-901", "stock": "7"}])
        assert seen == []

        # Обратный случай: по снимку товар был в наличии, а на деле уже разобран.
        Product.objects.filter(pk=product.pk).update(available_quantity=Decimal("5"))

        def racing_sold_out(item, maps):
            Product.objects.filter(pk=product.pk).update(available_quantity=Decimal("0"))
            return real(item, maps)

        with (
            mock.patch.object(matching, "resolve_in_memory", side_effect=racing_sold_out),
            django_capture_on_commit_callbacks(execute=True),
        ):
            use_cases.update_stocks([{"external_id": "1c-901", "stock": "7"}])
        assert seen == [("0", "7")]
    finally:
        events.product_stock_became_available.disconnect(dispatch_uid="b3-test")


def test_real_checkout_during_stock_update_keeps_its_reservation(cart_with_product):
    """Тот же сценарий без подмены счётчиков: настоящий ``place_order`` между чтением
    батча и записью строки, затем настоящая отмена."""
    from apps.orders.reservation import release_reservation
    from apps.orders.services import place_order

    cart, product = cart_with_product
    placed = {}
    real = matching.resolve_in_memory

    def racing(item, maps):
        if not placed:
            placed["order"] = place_order(
                cart,
                user=None,
                customer_data={"customer_name": "Гость", "customer_phone": "+79990001122"},
            )
        return real(item, maps)

    with mock.patch.object(matching, "resolve_in_memory", side_effect=racing):
        use_cases.update_stocks([{"external_id": product.code_1c, "stock": "10"}])

    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == Decimal("8")

    assert release_reservation(placed["order"].pk) is True
    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("0")
    assert product.available_quantity == Decimal("10")


def test_reservation_released_after_exchange_returns_exactly_what_was_held(product):
    """Сквозной сценарий: чекаут во время обмена, затем отмена заказа. Резерв не уходит
    в минус, а свободный остаток возвращается к физическому."""
    from apps.orders.models import Order, OrderItem, ReservationStatus
    from apps.orders.reservation import release_reservation

    order = Order.objects.create(
        order_number="RS-1", reservation_status=ReservationStatus.HELD, customer_phone="+7900"
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=2,
        price_final=Decimal("1000"),
        line_total=Decimal("2000"),
    )

    with _racing_match(product.pk):
        use_cases.update_stocks([{"external_id": CODE, "stock": "10"}])
    assert release_reservation(order.pk) is True

    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("0")
    assert product.available_quantity == Decimal("10")


# ═══════════ update_stocks_bulk (команда apply_stocks_1c) ═══════════


def test_bulk_stock_update_keeps_site_reservation(product):
    Product.objects.filter(pk=product.pk).update(
        reserved_quantity=Decimal("2"), available_quantity=Decimal("3")
    )

    _log, result = use_cases.update_stocks_bulk([{"external_id": CODE, "stock": "10"}])

    assert result.updated == 1
    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == Decimal("8")


def test_bulk_stock_update_reads_products_inside_the_write_transaction(product):
    """Чанк читается под замком внутри транзакции записи — окна между чтением и
    ``bulk_update`` нет. Проверяем по факту: к моменту записи соединение в транзакции,
    а товары выбраны с ``FOR UPDATE``."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        use_cases.update_stocks_bulk([{"external_id": CODE, "stock": "10"}])

    _assert_locked_before_update_and_own_columns_only(queries)


# ═══════════ products/import|update: пакетный путь и построчный fallback ═══════════


def _racing_rules(pk: int):
    """Побочный эффект между построением карт товаров и записью (фаза 1 → фаза 2)."""
    from apps.catalog import categorization

    race = _once(lambda: _checkout_and_edit(pk))
    real = categorization.load_active_rules

    def racing(*args, **kwargs):
        race()
        return real(*args, **kwargs)

    return mock.patch.object(categorization, "load_active_rules", side_effect=racing)


def test_bulk_import_keeps_reservation_and_content(product):
    with _racing_rules(product.pk):
        _log, result = use_cases.import_products(
            [{"external_id": CODE, "name": "Перф.ЗУБР", "price": "1200", "stock": "10"}]
        )

    assert result.updated == 1
    _assert_site_state_survived(product)
    assert product.price == Decimal("1200")
    assert product.stock_quantity == Decimal("10")
    assert product.available_quantity == Decimal("8")
    assert product.original_name == "Перф.ЗУБР"  # поля 1С при этом записаны


def test_bulk_import_row_without_stock_does_not_roll_back_available(product):
    """В строке только цена: счётчики остатка обмен не трогает вовсе — в том числе
    не возвращает их к значениям, прочитанным в начале батча."""
    with _racing_rules(product.pk):
        use_cases.import_products([{"external_id": CODE, "name": "Перф.ЗУБР", "price": "1200"}])

    _assert_site_state_survived(product)
    assert product.available_quantity == Decimal("3")
    assert product.stock_quantity == Decimal("5")


def test_bulk_import_does_not_roll_back_price_and_brand(product):
    """Пока шёл импорт, прайс сменил цену, а менеджер проставил бренд. В строке
    импорта цены нет, а правило «бренд, если пусто» решалось по устаревшему
    значению — оба поля откатывались."""
    from apps.catalog import categorization

    def concurrent_changes():
        Product.objects.filter(pk=product.pk).update(price=Decimal("1500"), brand="ЗУБР")

    race = _once(concurrent_changes)
    real = categorization.load_active_rules

    def racing(*args, **kwargs):
        race()
        return real(*args, **kwargs)

    with mock.patch.object(categorization, "load_active_rules", side_effect=racing):
        use_cases.import_products([{"external_id": CODE, "name": "Перф.", "brand": "Bosch"}])

    product.refresh_from_db()
    assert product.price == Decimal("1500")
    assert product.brand == "ЗУБР"  # уже заполнен — 1С его не перезаписывает


def test_bulk_import_writes_nothing_for_unchanged_products(product):
    """Строка ничего не меняет — товар не пишется вовсе (и не откатывается к снимку)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        _log, result = use_cases.import_products([{"external_id": CODE}])

    assert result.updated == 1  # строка учтена
    assert not [q for q in queries if q["sql"].startswith('UPDATE "catalog_product"')]


def test_bulk_import_duplicate_of_new_product_stays_on_bulk_path():
    """Две строки с одним новым кодом: вторая — обновление только что созданного
    товара. Пакет не должен из-за этого уходить на построчный путь."""
    with mock.patch.object(
        use_cases, "_run_rows_per_row", side_effect=AssertionError("ушли на построчный путь")
    ):
        _log, result = use_cases.import_products(
            [
                {"external_id": "1c-new", "name": "Дрель", "price": "100", "stock": "3"},
                {"external_id": "1c-new", "name": "Дрель", "price": "150", "stock": "5"},
            ]
        )

    assert (result.created, result.updated) == (1, 1)
    created = Product.objects.get(code_1c="1c-new")
    assert created.price == Decimal("150")
    assert created.available_quantity == Decimal("5")


def test_bulk_import_twin_matches_update_one_row(product):
    """Один товар найден дважды — по коду и по артикулу (карты строятся разными
    запросами, объекты разные). Обе строки применяются к одной свежей строке."""
    Product.objects.filter(pk=product.pk).update(article="ART-900")

    use_cases.import_products(
        [
            {"external_id": CODE, "name": "Перф.", "stock": "10"},
            {"sku": "ART-900", "name": "Перф.", "price": "1700"},
        ]
    )

    product.refresh_from_db()
    assert product.stock_quantity == Decimal("10")
    assert product.price == Decimal("1700")


def test_file_import_is_processed_in_batches(monkeypatch):
    """Файловый импорт отдаёт файл целиком. Запись идёт под замком строк товаров,
    поэтому — пачками: иначе весь каталог был бы заблокирован на всё время записи."""
    monkeypatch.setattr(bulk_import, "BATCH", 2)
    sizes = []
    real = bulk_import.run_rows_bulk

    def spy(raw_items, **kwargs):
        sizes.append(len(raw_items))
        return real(raw_items, **kwargs)

    monkeypatch.setattr(bulk_import, "run_rows_bulk", spy)
    rows = [{"external_id": f"1c-b{i}", "name": f"Товар {i}", "price": "10"} for i in range(5)]

    _log, result = use_cases.import_products(rows)

    assert sizes == [2, 2, 1]
    assert result.created == 5
    assert Product.objects.filter(code_1c__startswith="1c-b").count() == 5


@pytest.mark.parametrize(
    "run",
    [
        lambda: use_cases.update_stocks([{"external_id": CODE, "stock": "10"}]),
        lambda: use_cases.update_stocks_bulk([{"external_id": CODE, "stock": "10"}]),
        lambda: use_cases.import_products([{"external_id": CODE, "name": "П", "stock": "10"}]),
        lambda: stock.update_stock(normalizers.normalize_item({"external_id": CODE, "stock": "9"})),
    ],
    ids=["stocks/update", "update_stocks_bulk", "products/import", "shim"],
)
def test_every_stock_writer_locks_first_and_writes_own_columns(product, run):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        run()

    _assert_locked_before_update_and_own_columns_only(queries)


def test_per_row_fallback_locks_first_and_writes_own_columns(product):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with (
        mock.patch.object(bulk_import, "run_rows_bulk", return_value=False),
        CaptureQueriesContext(connection) as queries,
    ):
        use_cases.import_products([{"external_id": CODE, "name": "П", "stock": "10"}])

    _assert_locked_before_update_and_own_columns_only(queries)


def test_per_row_fallback_keeps_reservation_and_content(product):
    """Пакетный путь упал — работает построчный. Гарантии те же."""
    with (
        mock.patch.object(bulk_import, "run_rows_bulk", return_value=False),
        _racing_rules(product.pk),
    ):
        _log, result = use_cases.import_products(
            [{"external_id": CODE, "name": "Перф.ЗУБР", "price": "1200", "stock": "10"}]
        )

    assert result.updated == 1
    _assert_site_state_survived(product)
    assert product.available_quantity == Decimal("8")
    assert product.price == Decimal("1200")


# ═══════════ точечные функции ═══════════


def test_stock_shim_keeps_site_reservation(product):
    Product.objects.filter(pk=product.pk).update(
        reserved_quantity=Decimal("2"), available_quantity=Decimal("3")
    )

    assert stock.update_stock(normalizers.normalize_item({"external_id": CODE, "stock": "10"}))

    product.refresh_from_db()
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == Decimal("8")


def test_exchange_never_lists_site_reservation_among_its_fields():
    """Счётчик резерва сайта не должен появиться ни в одном списке полей записи."""
    from apps.sync_1c import product_writer

    for fields in (
        stock._STOCK_FIELDS,
        pricing._PRICE_FIELDS,
        product_writer._TRACKED_FIELDS,
        product_writer._UPDATE_FIELDS,
        bulk_import._PRODUCT_UPDATE_FIELDS,
    ):
        assert "reserved_quantity" not in fields


def test_bulk_import_product_deleted_between_phases_is_a_row_error(product):
    """Товар удалили, пока шёл импорт: строка — ошибка, а не «обновлено» со ссылкой
    на несуществующий товар; остальные строки пачки записаны."""
    from apps.catalog import categorization
    from apps.sync_1c.models import NomenclatureStaging, StagingStatus

    other = Product.objects.create(name="Дрель", code_1c="1c-902", slug="drel-902")
    race = _once(lambda: Product.objects.filter(pk=product.pk).delete())
    real = categorization.load_active_rules

    def racing(*args, **kwargs):
        race()
        return real(*args, **kwargs)

    with (
        mock.patch.object(categorization, "load_active_rules", side_effect=racing),
        mock.patch.object(
            use_cases, "_run_rows_per_row", side_effect=AssertionError("ушли на построчный путь")
        ),
    ):
        _log, result = use_cases.import_products(
            [
                {"external_id": CODE, "name": "Перф.", "price": "1200"},
                {"external_id": "1c-902", "name": "Дрель", "price": "700"},
            ]
        )

    assert (result.updated, result.errors) == (1, 1)
    other.refresh_from_db()
    assert other.price == Decimal("700")
    failed = NomenclatureStaging.objects.get(code_1c=CODE)
    assert failed.status == StagingStatus.ERROR and failed.product_id is None


def test_available_is_clamped_when_site_holds_more_than_1c_has(product):
    """Под заказами сайта удержано больше, чем есть по данным 1С: ноль и предупреждение."""
    Product.objects.filter(pk=product.pk).update(reserved_quantity=Decimal("3"))

    with mock.patch.object(stock.logger, "warning") as warning:
        use_cases.update_stocks([{"external_id": CODE, "stock": "1"}])

    product.refresh_from_db()
    assert product.available_quantity == Decimal("0")
    assert product.reserved_quantity == Decimal("3")
    warning.assert_called_once()
    assert "удержано больше" in warning.call_args.args[0]


def test_reserve_of_1c_above_stock_is_not_worth_a_warning(product):
    """«Резерв 1С больше остатка» — обычное дело: в ноль зажимаем молча."""
    with mock.patch.object(stock.logger, "warning") as warning:
        use_cases.update_stocks([{"external_id": CODE, "stock": "1", "reserved": "4"}])

    warning.assert_not_called()
    product.refresh_from_db()
    assert product.available_quantity == Decimal("0")


def test_error_lines_stay_capped_across_batches(monkeypatch):
    """Пачек много, а журнал ошибок прогона по-прежнему ограничен."""
    monkeypatch.setattr(bulk_import, "BATCH", 40)
    rows = [{"name": f"Без идентификатора {i}"} for i in range(120)]

    log, result = use_cases.import_products(rows)

    assert result.errors == 120
    assert len((log.error_details or "").splitlines()) <= use_cases._MAX_ERROR_LINES + 1


def test_counters_merge_when_one_batch_falls_back(monkeypatch):
    """Одна пачка упала на пакетном пути и прошла построчно — счётчики прогона общие."""
    monkeypatch.setattr(bulk_import, "BATCH", 2)
    real = bulk_import.run_rows_bulk
    calls = []

    def flaky(raw_items, **kwargs):
        calls.append(len(raw_items))
        if len(calls) == 2:
            return False
        return real(raw_items, **kwargs)

    monkeypatch.setattr(bulk_import, "run_rows_bulk", flaky)
    rows = [{"external_id": f"1c-m{i}", "name": f"Товар {i}", "price": "10"} for i in range(5)]

    _log, result = use_cases.import_products(rows)

    assert result.created == 5 and result.errors == 0
    assert Product.objects.filter(code_1c__startswith="1c-m").count() == 5
