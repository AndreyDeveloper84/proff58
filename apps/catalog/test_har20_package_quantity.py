"""ХАР-20: разделение «предметов в наборе» и «количества в упаковке».

Владелец решил: у ``str-skoby`` «N шт» — это фасовка коробки, а не состав набора,
поэтому заводится отдельная числовая ось ``package_quantity`` («Количество в
упаковке», ед. «шт.»). Глобально ``piece_count`` не меняется: у наборов отвёрток
(160 PAV на стенде) и шарошек (5 PAV) «N шт» — это действительно предметы набора.

Corrective-миграция исполняется ШТАТНЫМ движком, без ручного SQL:

* блок ``str-skoby`` объявляет ``package_quantity`` с прежним regex фасовки;
* ``piece_count`` остаётся объявленным в том же блоке — но как **TRANSITIONAL**
  правило со ``skip_if``, из-за которого извлечение невозможно by construction.
  Тогда managed-множество блока по-прежнему содержит ``piece_count``, движок
  «больше не извлекает» его, и штатный prune удаляет ровно старые PAV
  (``source=regex`` ∈ ``PRUNABLE_SOURCES``) в той же транзакции, в которой
  создаётся ``package_quantity``;
* после corrective прогона transitional-правило из ruleset УДАЛЯЕТСЯ.

Миграция на стенде выполнена, поэтому в боевом ``data/attribute_rules.json``
transitional-правила уже нет. Прогон миграции тесты воспроизводят через фикстуру
``corrective``: она собирает ruleset одного corrective-прогона программно и
отдаёт его команде через ``--path``. Кейсы, проверяющие ПОСТОЯННОЕ состояние
(1–4, 14), работают против боевого файла — иначе расхождение «данные
мигрированы, правила нет» прошло бы мимо тестов.

Доказательство невозможности извлечения (тест
``test_transitional_piece_count_never_extracts_any_name``): для любого имени либо
«шт» стоит на границе слова — тогда срабатывает ``skip_if`` и правило целиком не
применяется; либо перед «шт» стоит словосимвол — тогда regex, требующий ``\\s+``
непосредственно перед «шт», совпасть не может.
"""

from __future__ import annotations

import json
import random
import shutil
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    Source,
)

SKOBY = "str-skoby"
OTVERTKI = "nabory-otvertok"
SHAROSHKI = "sharoshki"
MOLOTKI = "molotki"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Реальные имена со стенда (все 22 товара корректирующего scope) и ожидаемая фасовка.
STAGING_22 = [
    (37737, "Скобы для степлера ТИП 140  RAPID  6мм проф супертвердые (G/11/57),5000 шт", 5000),
    (37738, "Скобы для степлера ТИП 140  RAPID  8мм проф супертвердые (G/11/57),5000 шт", 5000),
    (37739, "Скобы для степлера ТИП 140  RAPID 10мм проф супертвердые (G/11/57),5000 шт", 5000),
    (37743, "Скобы для степлера тип 20GA(53F/D/056) ЗУБР  10мм 5000шт", 5000),
    (37744, "Скобы для степлера тип 20GA(53F/D/056) ЗУБР  13мм 5000шт", 5000),
    (37745, "Скобы для степлера тип 20GA(53F/D/056) ЗУБР  16мм 5000шт", 5000),
    (37746, "Скобы для степлера тип 20GA(53F/D/056) ЗУБР  19мм 5000шт", 5000),
    (37747, "Скобы для степлера тип 20GA(53F/D/056) ЗУБР  22мм 5000шт", 5000),
    (37749, "Скобы для степлера тип 53 FIT  6мм/1000шт", 1000),
    (37754, "Скобы для степлера ТИП 53 RAPID  6мм проф супертвердые (A/10JT21) ,5000 шт", 5000),
    (37758, "Скобы для степлера тип 53 ЗУБР  6мм/1000шт", 1000),
    (37759, "Скобы для степлера тип 53 ЗУБР  8мм/1000шт", 1000),
    (37760, "Скобы для степлера тип 53 ЗУБР 10мм/1000шт", 1000),
    (37761, "Скобы для степлера тип 53 ЗУБР 12мм/1000шт", 1000),
    (37762, "Скобы для степлера тип 53 ЗУБР 14мм/1000шт", 1000),
    (37763, "Скобы для степлера тип 55 (18GA)ЗУБР  15 мм, 2500шт", 2500),
    (37764, "Скобы для степлера тип 55 (18GA)ЗУБР  20 мм, 2500шт", 2500),
    (37765, "Скобы для степлера тип 55 (18GA)ЗУБР  25 мм, 2500шт", 2500),
    (37766, "Скобы для степлера тип 55 (18GA)ЗУБР  30 мм, 2500шт", 2500),
    (37767, "Скобы для степлера тип 55 (18GA)ЗУБР  40 мм, 2500шт", 2500),
    (37771, "Скобы для степлера ТИП 80 RAPID  8мм проф (12/BeA 80/Prebena A/) ,5000 шт", 5000),
    (37772, "Скобы для степлера ТИП 80 RAPID 10мм проф (12/BeA 80/Prebena A/) ,5000 шт", 5000),
]


# --- вспомогательное ---------------------------------------------------------


def _ruleset() -> dict:
    return json.loads((DATA_DIR / "attribute_rules.json").read_text(encoding="utf-8"))


def _block(raw: dict, tool_type: str) -> dict:
    return next(t for t in raw["tool_types"] if t["tool_type"] == tool_type)


def _managed_by_tt(raw: dict) -> dict[str, set[str]]:
    """Managed-множество ровно так, как его считает ``enrich_attributes``."""
    return {t["tool_type"]: {a["slug"] for a in t["attributes"]} for t in raw["tool_types"]}


def _write_ruleset(tmp_path: Path, raw: dict, name: str = "data") -> Path:
    """Каталог с подменённым attribute_rules.json для ``--path``."""
    base = tmp_path / name
    base.mkdir(exist_ok=True)
    for src in DATA_DIR.glob("*.json"):
        # Реестр карантина не копируем: он ссылается на боевые product_id, которых
        # в тестовой БД нет, а enrich_attributes на неизвестный товар падает
        # (контракт P2 — fail-closed). Карантин проверяется своим модулем тестов.
        if src.name == "attribute_quarantine.json":
            continue
        shutil.copy(src, base / src.name)
    (base / "attribute_rules.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return base


#: transitional-правило corrective-прогона. В ПОСТОЯННОМ ruleset его нет — по
#: контракту ХАР-20 §6 оно удаляется сразу после миграции, иначе `load_attributes`
#: при каждом деплое снова создавал бы привязку `piece_count ↔ «Скобы и стержни
#: клеевые»` и возвращал бы на витрину пустой фасет «Предметов в наборе».
#: Тесты строят его программно — так механика остаётся под проверкой, а
#: одноразовое правило не живёт в боевом файле.
TRANSITIONAL_PIECE_COUNT = {
    "slug": "piece_count",
    "name": "Предметов в наборе",
    "kind": "number",
    "unit": "шт",
    "source": "regex",
    "priority": 40,
    "is_filter": True,
    "_note": "TRANSITIONAL (ХАР-20): удерживает piece_count в managed-множестве блока.",
    "skip_if": ["шт"],
    "regex": ["(?<!\\d)(\\d{3,5})\\s+шт"],
}


def _corrective_ruleset(raw: dict) -> dict:
    """Ruleset одного corrective-прогона: постоянный + transitional ``piece_count``.

    Извлечение им невозможно by construction (``skip_if`` + ``\\s+`` перед «шт»),
    но ``piece_count`` попадает в managed-множество блока, и штатный prune видит
    старые PAV.
    """
    _block(raw, SKOBY)["attributes"].append(dict(TRANSITIONAL_PIECE_COUNT))
    return raw


def _rollback_ruleset(raw: dict) -> dict:
    """Зеркальный ruleset отката: piece_count снова извлекается, package_quantity глушится.

    Именно так откат исполняется штатным движком: ``package_quantity`` обязан
    остаться в managed-множестве блока, иначе prune его не увидит и PAV осиротеют.
    """
    block = _block(raw, SKOBY)
    attrs = []
    for a in block["attributes"]:
        a = dict(a)
        if a["slug"] == "package_quantity":
            a["skip_if"] = ["шт"]
            a["regex"] = ["(?<!\\d)(\\d{3,5})\\s+шт"]
            a["_note"] = "TRANSITIONAL (откат ХАР-20)."
        attrs.append(a)
    restored = dict(TRANSITIONAL_PIECE_COUNT)
    restored.pop("skip_if")
    restored["regex"] = ["(?<!\\d)(\\d{3,5})\\s*шт"]
    restored["_note"] = "Возврат к состоянию до ХАР-20."
    attrs.append(restored)
    block["attributes"] = attrs
    return raw


def _pav_map(product_ids, slug: str) -> dict[int, Decimal]:
    return {
        pav.product_id: pav.value_decimal
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=product_ids, attribute__slug=slug
        )
    }


def _dry_run(*args) -> dict:
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", *args, stdout=out, stderr=err)
    return json.loads(out.getvalue())


@pytest.fixture
def catalog(db):
    """Категория + опции tool_type для четырёх типов, участвующих в тестах."""
    root = Category.add_root(name="Каталог", slug="katalog", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    options = {
        slug: AttributeOption.objects.create(attribute=tool_type, value=slug, slug=slug)
        for slug in (SKOBY, OTVERTKI, SHAROSHKI, MOLOTKI)
    }
    call_command("load_attributes")
    return {"root": root, "tool_type": tool_type, "options": options}


def _make_product(catalog, name, code, *, tool_type=SKOBY, stock="5", is_active=True):
    product = Product.objects.create(
        category=catalog["root"],
        name=name,
        slug=code,
        code_1c=code,
        available_quantity=Decimal(stock),
        is_active=is_active,
    )
    ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["options"][tool_type],
        source=Source.MANUAL,
    )
    return product


def _seed_legacy_piece_count(product, value: int) -> ProductAttributeValue:
    """Старый (ошибочный) PAV фасовки на оси piece_count — как он лежит на стенде."""
    pav = ProductAttributeValue.objects.create(
        product=product,
        attribute=Attribute.objects.get(slug="piece_count"),
        value_decimal=Decimal(value),
        source=Source.REGEX,
    )
    cache = dict(product.attrs_cache or {})
    cache["piece_count"] = float(value)
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    return pav


@pytest.fixture
def corrective(tmp_path) -> tuple[str, str]:
    """Аргументы ОДНОГО corrective-прогона: ``--path`` на ruleset с transitional-правилом.

    Постоянный ruleset transitional-правила не содержит, поэтому прогон миграции
    воспроизводится через подменённый каталог правил — механика остаётся под
    проверкой, а одноразовое правило не живёт в боевом файле.
    """
    base = _write_ruleset(tmp_path, _corrective_ruleset(_ruleset()), name="corrective")
    return ("--path", str(base))


@pytest.fixture
def skoby_22(catalog):
    """22 товара корректирующего scope с уже проставленным ошибочным piece_count."""
    products = []
    for pid, name, value in STAGING_22:
        product = _make_product(catalog, name, f"sk-{pid}")
        _seed_legacy_piece_count(product, value)
        products.append(product)
    return products


# =============================================================================
# EXTRACTION
# =============================================================================


def test_str_skoby_extracts_package_quantity():
    """1. У скоб фасовка извлекается в package_quantity — на всех 22 боевых именах."""
    rules = AttributeRules.from_dict(_ruleset())

    got = {}
    for pid, name, _ in STAGING_22:
        got[pid] = {v.slug: v.number for v in rules.extract(SKOBY, name)}

    assert all("package_quantity" in v for v in got.values())
    assert [int(got[pid]["package_quantity"]) for pid, _, _ in STAGING_22] == [
        value for _, _, value in STAGING_22
    ]


def test_str_skoby_no_longer_produces_piece_count():
    """2. Ни одно из 22 боевых имён больше не даёт piece_count."""
    rules = AttributeRules.from_dict(_ruleset())

    offenders = [
        pid
        for pid, name, _ in STAGING_22
        if any(v.slug == "piece_count" for v in rules.extract(SKOBY, name))
    ]

    assert offenders == []


def test_set_of_114_pieces_is_not_globally_package_quantity():
    """3. «Набор отверток и бит 114 шт» остаётся piece_count, а не фасовкой.

    Ось ``package_quantity`` подключена ровно к одному подтверждённому tool_type;
    глобальной трактовки «N шт = фасовка» не появляется.
    """
    raw = _ruleset()
    rules = AttributeRules.from_dict(raw)

    values = {v.slug: v.number for v in rules.extract(OTVERTKI, "Набор отверток и бит 114 шт")}
    owners = [
        t["tool_type"]
        for t in raw["tool_types"]
        if any(a["slug"] == "package_quantity" for a in t["attributes"])
    ]

    assert values["piece_count"] == Decimal(114)
    assert "package_quantity" not in values
    assert owners == [SKOBY]


# =============================================================================
# MIGRATION
# =============================================================================


def test_transitional_rule_keeps_piece_count_in_managed_set():
    """4. piece_count в managed-множестве str-skoby — только на corrective прогон.

    Два состояния ruleset, оба обязательны:

    * corrective — ``piece_count`` объявлен, иначе штатный prune слеп и 22 старых
      PAV осиротеют рядом с новым ``package_quantity``;
    * постоянный — ``piece_count`` у скоб больше нет, иначе ``load_attributes`` на
      каждом деплое возвращал бы привязку `piece_count ↔ «Скобы и стержни клеевые»`
      и пустой фасет «Предметов в наборе» на витрину.
    """
    permanent = _managed_by_tt(_ruleset())
    corrective = _managed_by_tt(_corrective_ruleset(_ruleset()))

    assert corrective[SKOBY] == {"length", "package_quantity", "piece_count"}
    assert permanent[SKOBY] == {"length", "package_quantity"}
    # Блоки-владельцы «настоящего» piece_count не тронуты ни в одном состоянии.
    assert "piece_count" in permanent[OTVERTKI]
    assert "piece_count" in permanent[SHAROSHKI]


def test_transitional_piece_count_never_extracts_any_name():
    """5. Transitional-правило не создаёт НИ ОДНОГО нового piece_count.

    Проверяем и целевые формы фасовки, и фаззинг по алфавиту, из которого
    собираются реальные имена скоб. Ruleset — именно corrective: на постоянном
    правила ``piece_count`` у скоб нет вовсе, и проверка была бы вхолостую.
    """
    rules = AttributeRules.from_dict(_corrective_ruleset(_ruleset()))

    targeted = [
        "скобы 5000 шт",
        "скобы 5000шт",
        "скобы 5000  шт",
        "скобы 5000\tшт",
        "скобы 1000ШТ",
        "скобы, 2500шт.",
        "500шт",
        "abc500 шт",
        "Скоба 04 мм тип 80 (50400шт)",
    ]
    random.seed(2026)
    alphabet = "абвгдешт0123456789 .,/()-мм"
    fuzz = [
        "".join(random.choice(alphabet) for _ in range(random.randint(3, 40))) for _ in range(20000)
    ]

    hits = [
        name
        for name in targeted + fuzz + [n for _, n, _ in STAGING_22]
        if any(v.slug == "piece_count" for v in rules.extract(SKOBY, name))
    ]

    assert hits == []


@pytest.mark.django_db
def test_prune_removes_legacy_piece_count(skoby_22, corrective):
    """6. Штатный prune удаляет старый piece_count ровно у целевых скоб."""
    ids = [p.id for p in skoby_22]
    assert len(_pav_map(ids, "piece_count")) == 22

    call_command(
        "enrich_attributes", "--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective
    )

    assert _pav_map(ids, "piece_count") == {}


@pytest.mark.django_db
def test_package_quantity_created_with_same_numeric_value(skoby_22, corrective):
    """7. package_quantity создаётся с тем же числом: 1000→1000, 5000→5000."""
    ids = [p.id for p in skoby_22]
    before = _pav_map(ids, "piece_count")

    call_command(
        "enrich_attributes", "--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective
    )

    after = _pav_map(ids, "package_quantity")
    assert len(after) == 22
    assert after == before


@pytest.mark.django_db
def test_create_and_prune_are_atomic(skoby_22, monkeypatch, corrective):
    """8. Создание package_quantity и удаление piece_count — одна транзакция.

    Роняем команду на последнем шаге (сброс attrs_cache), уже ПОСЛЕ того как
    delete/bulk_create выполнены: промежуточного состояния «два фасета сразу»
    остаться не должно — откатывается всё.
    """
    from apps.catalog.management.commands import enrich_attributes as cmd

    ids = [p.id for p in skoby_22]

    def boom(*args, **kwargs):
        raise RuntimeError("сбой после записи, до коммита")

    monkeypatch.setattr(cmd, "flush_attrs_cache_merged", boom)

    with pytest.raises(RuntimeError):
        call_command(
            "enrich_attributes",
            "--tool-type",
            SKOBY,
            "--in-stock-only",
            "--active-only",
            *corrective,
        )

    assert len(_pav_map(ids, "piece_count")) == 22
    assert _pav_map(ids, "package_quantity") == {}


# =============================================================================
# ISOLATION
# =============================================================================


@pytest.mark.django_db
def test_nabory_otvertok_keeps_piece_count(catalog, skoby_22, corrective):
    """9. Наборы отвёрток продолжают жить на piece_count (160 PAV на стенде).

    Прогон — corrective и по всему каталогу: именно в нём prune ``piece_count``
    включён, и именно тут чужой PAV мог бы пострадать.
    """
    product = _make_product(catalog, "Набор отверток и бит 114 шт", "no-114", tool_type=OTVERTKI)
    _seed_legacy_piece_count(product, 114)
    pav_id = ProductAttributeValue.objects.get(product=product, attribute__slug="piece_count").id

    call_command("enrich_attributes", "--in-stock-only", "--active-only", *corrective)

    pav = ProductAttributeValue.objects.get(product=product, attribute__slug="piece_count")
    assert pav.id == pav_id
    assert pav.value_decimal == Decimal(114)
    assert not ProductAttributeValue.objects.filter(
        product=product, attribute__slug="package_quantity"
    ).exists()


@pytest.mark.django_db
def test_sharoshki_keep_piece_count(catalog, skoby_22, corrective):
    """10. Шарошки продолжают жить на piece_count (5 PAV на стенде)."""
    product = _make_product(
        catalog, "Набор шарошек по металлу 5 предметов", "sh-5", tool_type=SHAROSHKI
    )
    _seed_legacy_piece_count(product, 5)

    call_command("enrich_attributes", "--in-stock-only", "--active-only", *corrective)

    pav = ProductAttributeValue.objects.get(product=product, attribute__slug="piece_count")
    assert pav.value_decimal == Decimal(5)
    assert not ProductAttributeValue.objects.filter(
        product=product, attribute__slug="package_quantity"
    ).exists()


@pytest.mark.django_db
def test_zero_stock_skoby_stays_out_of_corrective_scope(catalog, skoby_22, corrective):
    """11. Скобы с нулевым остатком в corrective scope не попадают.

    Владелец отложил остальные 40 позиций типа: их piece_count остаётся как есть
    до отдельного окна.
    """
    zero = _make_product(catalog, "Скобы для степлера тип 53 FIT  4мм/1000шт", "sk-zero", stock="0")
    _seed_legacy_piece_count(zero, 1000)

    report = _dry_run("--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective)
    call_command(
        "enrich_attributes", "--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective
    )

    assert zero.id not in {row["product_id"] for row in report["rows"]}
    assert report["scope"]["selected_products"] == 22
    survived = ProductAttributeValue.objects.get(product=zero, attribute__slug="piece_count")
    assert survived.value_decimal == Decimal(1000)


@pytest.mark.django_db
def test_other_tool_type_piece_count_not_pruned(catalog, skoby_22, corrective):
    """12. Товар чужого tool_type под prune не попадает.

    У ``molotki`` блок правил есть, но ``piece_count`` в нём не объявлен, значит
    атрибут вне managed-множества типа — движок его не трогает. Проверяем на
    corrective ruleset: transitional-правило добавлено только скобам.
    """
    hammer = _make_product(catalog, "Молоток слесарный 500 г", "ml-1", tool_type=MOLOTKI)
    _seed_legacy_piece_count(hammer, 3)
    assert "piece_count" not in _managed_by_tt(_corrective_ruleset(_ruleset()))[MOLOTKI]

    call_command("enrich_attributes", "--in-stock-only", "--active-only", *corrective)

    assert ProductAttributeValue.objects.get(
        product=hammer, attribute__slug="piece_count"
    ).value_decimal == Decimal(3)


@pytest.mark.django_db
def test_no_cross_tool_type_prune(catalog, skoby_22, corrective):
    """13. Прогон, ограниченный скобами, не удаляет ни одного чужого PAV."""
    others = []
    for name, code, tt, value in (
        ("Набор отверток и бит 114 шт", "x-otv", OTVERTKI, 114),
        ("Набор шарошек по металлу 5 предметов", "x-sh", SHAROSHKI, 5),
        ("Молоток слесарный 500 г", "x-ml", MOLOTKI, 3),
    ):
        product = _make_product(catalog, name, code, tool_type=tt)
        _seed_legacy_piece_count(product, value)
        others.append(product)
    other_ids = [p.id for p in others]
    before = _pav_map(other_ids, "piece_count")

    report = _dry_run("--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective)
    call_command(
        "enrich_attributes", "--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective
    )

    pruned_products = {row["product_id"] for row in report["rows"] if row["action"] == "prune"}
    assert pruned_products == {p.id for p in skoby_22}
    assert _pav_map(other_ids, "piece_count") == before
    assert _pav_map(other_ids, "package_quantity") == {}


# =============================================================================
# RELIABILITY
# =============================================================================


@pytest.mark.django_db
def test_rerun_is_idempotent(skoby_22, corrective):
    """14. После миграции штатный прогон на ПОСТОЯННОМ ruleset ничего не меняет.

    Это состояние стенда после мержа: миграция уже применена, transitional-правила
    в боевом файле нет. Любой штатный прогон обязан дать только ``keep`` — ни
    ``create`` (иначе вернутся 22 piece_count и на витрине окажутся два фасета
    сразу, что владелец прямо запретил), ни ``prune``, ни ``update``.
    """
    ids = [p.id for p in skoby_22]
    scope = ("--tool-type", SKOBY, "--in-stock-only", "--active-only")

    call_command("enrich_attributes", *scope, *corrective)
    snapshot = {
        (pav.product_id, pav.attribute.slug): (pav.id, pav.value_decimal)
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=ids, attribute__slug="package_quantity"
        ).select_related("attribute")
    }

    report = _dry_run(*scope)
    call_command("enrich_attributes", *scope)

    again = {
        (pav.product_id, pav.attribute.slug): (pav.id, pav.value_decimal)
        for pav in ProductAttributeValue.objects.filter(
            product_id__in=ids, attribute__slug="package_quantity"
        ).select_related("attribute")
    }
    assert again == snapshot
    assert set(report["totals"]["by_action"]) == {"keep"}
    assert _pav_map(ids, "piece_count") == {}


@pytest.mark.django_db
def test_rollback_restores_original_attribute_and_value(skoby_22, tmp_path, corrective):
    """15. Откат возвращает исходную пару «атрибут + значение».

    Откат исполняется тем же движком по зеркальному ruleset: piece_count снова
    извлекается, package_quantity глушится transitional-правилом и вычищается
    штатным prune (остаться в managed-множестве он обязан, иначе PAV осиротеют).
    """
    ids = [p.id for p in skoby_22]
    manifest = _pav_map(ids, "piece_count")
    args = ("--tool-type", SKOBY, "--in-stock-only", "--active-only")

    call_command("enrich_attributes", *args, *corrective)
    assert len(_pav_map(ids, "package_quantity")) == 22

    base = _write_ruleset(tmp_path, _rollback_ruleset(_ruleset()))
    call_command("enrich_attributes", *args, "--path", str(base))

    assert _pav_map(ids, "piece_count") == manifest
    assert _pav_map(ids, "package_quantity") == {}


@pytest.mark.django_db
def test_attrs_cache_matches_db_after_migration(skoby_22, corrective):
    """16. attrs_cache после миграции соответствует БД: piece_count вычищен."""
    ids = [p.id for p in skoby_22]

    call_command(
        "enrich_attributes", "--tool-type", SKOBY, "--in-stock-only", "--active-only", *corrective
    )

    values = _pav_map(ids, "package_quantity")
    for product in Product.objects.filter(id__in=ids):
        cache = product.attrs_cache or {}
        assert "piece_count" not in cache
        assert Decimal(str(cache["package_quantity"])) == values[product.id]
