"""Shadow rules engine для tool_type (Phase 6.0, proposal-only).

Чистые вычисления без записи в БД: загрузка versioned ruleset из
``data/catalog_processing_rules/``, conjunctive сопоставление правил с
товарами, detection коллизий и подготовка shadow-отчёта.

Контур НЕ создаёт CatalogChange и не изменяет каталог; rules как
proposals (этап 6.1) включаются только после gate 6.0 отдельным решением.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from jsonschema import Draft7Validator, FormatChecker

from .processing import canonical_hash
from .tool_type import normalize

RULESET_PATH = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v1.json"
SCHEMA_PATH = Path(settings.BASE_DIR) / "apps" / "catalog" / "schemas" / "tool_type_ruleset_v1.json"

TIER_CANDIDATE = "candidate"
TIER_SHADOW_REGRESSION = "shadow_regression"


@dataclass(frozen=True)
class ShadowRule:
    rule_ref: str
    option_slug: str
    tier: str
    brand_any: tuple[str, ...]
    name_keywords_any: tuple[str, ...]
    source_group_any: tuple[str, ...]
    article_prefix_any: tuple[str, ...]
    negative_keywords: tuple[str, ...]
    derived_from: tuple[int, ...]


@dataclass(frozen=True)
class ShadowRuleset:
    ruleset_id: str
    version: int
    rules: tuple[ShadowRule, ...]
    negative_fixtures: tuple[dict, ...]
    ruleset_hash: str


@dataclass(frozen=True)
class ProductFacts:
    """Минимальный набор полей товара для сопоставления (без ORM-зависимости)."""

    product_id: int
    name: str = ""
    original_name: str = ""
    brand: str = ""
    source_group: str = ""
    article: str = ""
    has_tool_type: bool = False


@lru_cache(maxsize=1)
def _schema_validator() -> Draft7Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, format_checker=FormatChecker())


def load_ruleset(path: Path | None = None) -> ShadowRuleset:
    """Загрузить и провалидировать ruleset; hash — канонический SHA-256."""
    path = path or RULESET_PATH
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = sorted(_schema_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"Ruleset не соответствует схеме: {errors[0].message}")
    rules = tuple(_build_rule(r) for r in data["rules"])
    refs = [r.rule_ref for r in rules]
    if len(refs) != len(set(refs)):
        raise ValueError("Дубли rule_ref в ruleset")
    for r in rules:
        if not any((r.brand_any, r.name_keywords_any, r.source_group_any, r.article_prefix_any)):
            raise ValueError(f"Правило {r.rule_ref} без единого условия match")
    return ShadowRuleset(
        ruleset_id=data["ruleset_id"],
        version=data["version"],
        rules=rules,
        negative_fixtures=tuple(data.get("negative_fixtures", [])),
        ruleset_hash=canonical_hash(data),
    )


def _build_rule(raw: dict) -> ShadowRule:
    match = raw.get("match", {})
    return ShadowRule(
        rule_ref=raw["rule_ref"],
        option_slug=raw["option_slug"],
        tier=raw.get("tier", TIER_CANDIDATE),
        brand_any=tuple(normalize(b) for b in match.get("brand_any", [])),
        name_keywords_any=tuple(normalize(k) for k in match.get("name_keywords_any", [])),
        source_group_any=tuple(normalize(g) for g in match.get("source_group_any", [])),
        article_prefix_any=tuple(normalize(p) for p in match.get("article_prefix_any", [])),
        negative_keywords=tuple(normalize(k) for k in raw.get("negative_keywords", [])),
        derived_from=tuple(raw.get("derived_from", [])),
    )


@dataclass(frozen=True)
class ProductVerdict:
    product_id: int
    status: str  # prediction | collision | excluded_existing_tool_type | no_match
    option_slug: str = ""
    rule_refs: tuple[str, ...] = ()
    slugs: tuple[str, ...] = ()


def _haystack(facts: ProductFacts) -> str:
    """1С-имя приоритетно (конвенция legacy enrich); fallback на витринное."""
    return normalize(facts.original_name or facts.name)


def rule_matches(rule: ShadowRule, facts: ProductFacts) -> bool:
    haystack = _haystack(facts)
    if rule.negative_keywords and any(k in haystack for k in rule.negative_keywords):
        return False
    if rule.brand_any and normalize(facts.brand) not in rule.brand_any:
        return False
    if rule.name_keywords_any and not any(k in haystack for k in rule.name_keywords_any):
        return False
    if rule.source_group_any and normalize(facts.source_group) not in rule.source_group_any:
        return False
    if rule.article_prefix_any and not any(
        normalize(facts.article).startswith(p) for p in rule.article_prefix_any
    ):
        return False
    return True


def evaluate_product(rules, facts: ProductFacts) -> ProductVerdict:
    """Вердикт по товару. Existing tool_type исключается ДО матчинга
    (решение 3: перезапись запрещена, попыток быть не должно)."""
    if facts.has_tool_type:
        return ProductVerdict(facts.product_id, "excluded_existing_tool_type")
    hits = [r for r in rules if rule_matches(r, facts)]
    if not hits:
        return ProductVerdict(facts.product_id, "no_match")
    slugs = tuple(sorted({r.option_slug for r in hits}))
    refs = tuple(sorted(r.rule_ref for r in hits))
    if len(slugs) > 1:
        return ProductVerdict(facts.product_id, "collision", slugs=slugs, rule_refs=refs)
    return ProductVerdict(facts.product_id, "prediction", option_slug=slugs[0], rule_refs=refs)


def validate_against_taxonomy(ruleset: ShadowRuleset, allowed_slugs: set[str]) -> list[str]:
    """Slugs правил, отсутствующие в allowed options (должно быть пусто)."""
    return sorted({r.option_slug for r in ruleset.rules} - allowed_slugs)


def check_negative_fixtures(ruleset: ShadowRuleset) -> list[str]:
    """Каждая negative fixture обязана давать no_match по всем правилам."""
    violations = []
    for i, fix in enumerate(ruleset.negative_fixtures):
        facts = ProductFacts(
            product_id=-(i + 1),
            original_name=fix.get("name", ""),
            brand=fix.get("brand", ""),
            source_group=fix.get("source_group", ""),
            article=fix.get("article", ""),
        )
        for r in ruleset.rules:
            if rule_matches(r, facts):
                violations.append(
                    f"negative_fixture[{i}] {fix.get('name')!r} матчится правилом {r.rule_ref}"
                )
    return violations
