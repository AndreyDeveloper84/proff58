"""End-to-end понижение версии на РЕАЛЬНОМ каноническом манифесте (Wave 7.1 / H5).

Материал взят из H4: четыре опции с нулевым usage (`metchiki`, `plashki`,
`osnastka-rezbonarez`, `hoz-schetchiki`) были осознанно оставлены в словаре как
естественный тестовый материал для процедуры удаления и отката.

Проверяется главное свойство процедуры: после выполнения всех шагов
``taxonomy_identity_hash`` живого словаря совпадает с identity целевого манифеста
N-1 — то есть БД действительно приземлилась на предыдущую версию, а не «примерно
на неё».
"""

import json

import pytest
from django.core.management import call_command

from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue
from apps.catalog.taxonomy_manifest import (
    MANIFEST_PATH,
    manifest_semantic_hash,
    taxonomy_identity_hash,
)
from apps.catalog.taxonomy_reverse import (
    build_downgrade_plan,
    drop_disappearing_options,
    snapshot_pair_for_remap,
)
from apps.catalog.tool_type_rollback import (
    apply_rollback,
    live_taxonomy_identity,
    plan_rollback,
    verify_post_state,
)

pytestmark = pytest.mark.django_db

# H4 §9: оставлены как пробел ассортимента, 0 товаров на staging.
UNUSED_IN_H4 = ["hoz-schetchiki", "metchiki", "osnastka-rezbonarez", "plashki"]


def _write(tmp_path, name, doc):
    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


@pytest.fixture
def canonical_pair(tmp_path):
    """Пара манифестов: реальный canonical как N=2 и он же без 4 опций как N=1."""
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert base["manifest_version"] == 1
    assert len(base["options"]) == 336

    upper = dict(base, manifest_version=2)
    lower = dict(
        base,
        manifest_version=1,
        options=[o for o in base["options"] if o["slug"] not in UNUSED_IN_H4],
    )
    assert len(lower["options"]) == 332
    return _write(tmp_path, "canonical.v2.json", upper), _write(
        tmp_path, "canonical.v1.json", lower
    )


@pytest.fixture
def seeded(canonical_pair):
    call_command("load_tool_types", manifest=canonical_pair[0], verbosity=0)
    return canonical_pair


def _product(slug, option):
    attribute = Attribute.objects.get(slug="tool_type")
    product = Product.objects.create(slug=slug, original_name=slug, name=slug)
    ProductAttributeValue.objects.create(product=product, attribute=attribute, value_option=option)
    product.attrs_cache = {"tool_type": option.value}
    product.save(update_fields=["attrs_cache"])
    return product


def test_seed_reproduces_canonical_identity_hash(seeded):
    base = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert AttributeOption.objects.filter(attribute__slug="tool_type").count() == 336
    assert live_taxonomy_identity() == base["taxonomy_identity_hash"]


def test_downgrade_drops_four_unused_options_and_lands_on_target_identity(seeded, tmp_path):
    upper, lower = seeded
    plan = build_downgrade_plan(from_manifest=upper, to_manifest=lower)

    assert plan.feasible is True
    assert plan.summary["drop"] == 4
    assert plan.summary["keep"] == 332
    assert plan.summary["blocked"] == 0
    assert sorted(e["slug"] for e in plan.entries_by_disposition("drop")) == UNUSED_IN_H4

    result = drop_disappearing_options(plan, apply=True)

    assert result["dropped"] == UNUSED_IN_H4
    assert AttributeOption.objects.filter(attribute__slug="tool_type").count() == 332
    assert live_taxonomy_identity() == plan.to_manifest.identity_hash


def test_products_on_disappearing_option_block_the_downgrade(seeded):
    upper, lower = seeded
    _product("p1", AttributeOption.objects.get(slug="metchiki"))

    plan = build_downgrade_plan(from_manifest=upper, to_manifest=lower)

    assert plan.feasible is False
    assert [b["code"] for b in plan.blocking] == ["orphaned_products"]
    assert AttributeOption.objects.filter(slug="metchiki").exists()


def test_full_procedure_with_remap_lands_on_target_identity(seeded):
    """Четыре шага процедуры: план → перенос товаров → удаление опций → сверка.

    Цель переноса выбрана произвольно ради демонстрации механики — продуктового
    решения о слиянии типов здесь не принимается и в манифест ничего не пишется.
    """
    upper, lower = seeded
    p1 = _product("p1", AttributeOption.objects.get(slug="metchiki"))
    target = AttributeOption.objects.get(slug="prochaya-osnastka")

    plan = build_downgrade_plan(
        from_manifest=upper, to_manifest=lower, remap={"metchiki": target.slug}
    )
    assert plan.feasible is True
    assert plan.summary["affected_products"] == 1

    from_doc, to_doc = snapshot_pair_for_remap(plan)
    apply_rollback(plan_rollback(from_doc, to_doc))
    assert verify_post_state(to_doc)["passed"] is True

    result = drop_disappearing_options(plan, apply=True)

    assert result["dropped"] == UNUSED_IN_H4
    assert ProductAttributeValue.objects.get(product=p1).value_option.slug == target.slug
    assert Product.objects.get(id=p1.id).attrs_cache["tool_type"] == target.value
    assert live_taxonomy_identity() == plan.to_manifest.identity_hash
