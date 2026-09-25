"""Инвариант seed-файла tool_type: slug отображается ровно в одно value.

DEVIATION-2: «Степлеры и заклёпочники» и «Степлеры (скобозабивные)» имели
общий slug steplery — slug переставал быть функцией value. Повтор одной пары
(value, slug) в нескольких категориях ЛЕГАЛЕН (loader дедупит по value);
недопустим именно slug с >1 distinct value.
"""

from apps.catalog.ingest import data_dir
from apps.catalog.tool_type import ToolTypeRules


def _seed_slug_values() -> dict[str, set[str]]:
    rules = ToolTypeRules.from_file(f"{data_dir()}/tool_type_rules.json")
    slug_values: dict[str, set[str]] = {}
    for cat in rules.categories:
        for r in rules.options(cat.category):
            if r.slug:
                slug_values.setdefault(r.slug, set()).add(r.tool_type)
    return slug_values


def test_tool_type_seed_slug_maps_to_single_value():
    slug_values = _seed_slug_values()
    ambiguous = {slug: sorted(vals) for slug, vals in slug_values.items() if len(vals) > 1}
    assert ambiguous == {}, f"slug maps to multiple values in tool_type_rules.json: {ambiguous}"
