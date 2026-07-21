"""Shadow rules engine для tool_type (Phase 6.0, proposal-only).

Чистые вычисления без записи в БД: загрузка versioned ruleset из
``data/catalog_processing_rules/``, conjunctive сопоставление правил с
товарами, detection коллизий и подготовка shadow-отчёта.

Matcher v2 (P0.2/P1.1/P1.2): token-based keyword matching с prefix-покрытием
морфологии, раздельные поля ``original_name``/``name``, семантический
валидатор ruleset, rule-scoped negative fixtures, corpus loader и
gate-валидаторы sample/labels.

Контур НЕ создает CatalogChange и не изменяет каталог; rules как
proposals (этап 6.1) включаются только после gate 6.0 отдельным решением.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from jsonschema import Draft7Validator, FormatChecker

from .processing import canonical_hash
from .tool_type import normalize

RULESET_PATH = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v1.json"
SCHEMA_PATH = Path(settings.BASE_DIR) / "apps" / "catalog" / "schemas" / "tool_type_ruleset_v1.json"
CORPUS_SCHEMA_PATH = (
    Path(settings.BASE_DIR) / "apps" / "catalog" / "schemas" / "applied_tool_type_corpus_v1.json"
)

TIER_CANDIDATE = "candidate"
TIER_SHADOW_REGRESSION = "shadow_regression"

MATCHER_VERSION = "1.0"
MIN_KEYWORD_LEN = 3

_TOKEN_SPLIT = re.compile(r"[^0-9a-zа-я]+")


def tokenize(text: str | None) -> list[str]:
    """normalize → токены по не-буквенно-цифровым разделителям."""
    return [t for t in _TOKEN_SPLIT.split(normalize(text)) if t]


def keyword_matches_text(keyword: str, text: str) -> bool:
    """Однословный keyword: токен равен keyword или начинается с него.
    Многословный: токены keyword идут подряд, последний — prefix."""
    kw_tokens = tokenize(keyword)
    if not kw_tokens:
        return False
    tokens = tokenize(text)
    if len(kw_tokens) == 1:
        kw = kw_tokens[0]
        return any(t == kw or t.startswith(kw) for t in tokens)
    n = len(kw_tokens)
    for i in range(len(tokens) - n + 1):
        window = tokens[i : i + n]
        if all(w == k for w, k in zip(window[:-1], kw_tokens[:-1], strict=True)) and (
            window[-1] == kw_tokens[-1] or window[-1].startswith(kw_tokens[-1])
        ):
            return True
    return False


def _keywords_hit(keywords: tuple[str, ...], text: str) -> list[str]:
    return [k for k in keywords if keyword_matches_text(k, text)]


@dataclass(frozen=True)
class ShadowRule:
    rule_ref: str
    option_slug: str
    tier: str
    brand_any: tuple[str, ...]
    original_name_keywords_any: tuple[str, ...]
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
    matcher_version: str = MATCHER_VERSION


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
    """Загрузить и провалидировать ruleset (schema + семантика);
    hash — канонический SHA-256."""
    path = path or RULESET_PATH
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = sorted(_schema_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"Ruleset не соответствует схеме: {errors[0].message}")
    rules = tuple(_build_rule(r) for r in data["rules"])
    refs = [r.rule_ref for r in rules]
    if len(refs) != len(set(refs)):
        raise ValueError("Дубли rule_ref в ruleset")
    fixtures = tuple(data.get("negative_fixtures", []))
    _validate_semantics(rules, fixtures)
    return ShadowRuleset(
        ruleset_id=data["ruleset_id"],
        version=data["version"],
        rules=rules,
        negative_fixtures=fixtures,
        ruleset_hash=canonical_hash(data),
    )


def _build_rule(raw: dict) -> ShadowRule:
    match = raw.get("match", {})
    return ShadowRule(
        rule_ref=raw["rule_ref"],
        option_slug=raw["option_slug"],
        tier=raw.get("tier", TIER_CANDIDATE),
        brand_any=tuple(normalize(b) for b in match.get("brand_any", [])),
        original_name_keywords_any=tuple(
            normalize(k) for k in match.get("original_name_keywords_any", [])
        ),
        name_keywords_any=tuple(normalize(k) for k in match.get("name_keywords_any", [])),
        source_group_any=tuple(normalize(g) for g in match.get("source_group_any", [])),
        article_prefix_any=tuple(normalize(p) for p in match.get("article_prefix_any", [])),
        negative_keywords=tuple(normalize(k) for k in raw.get("negative_keywords", [])),
        derived_from=tuple(raw.get("derived_from", [])),
    )


_KEYWORD_DIMENSIONS = ("original_name_keywords_any", "name_keywords_any")
_DIMENSIONS = (
    "brand_any",
    "original_name_keywords_any",
    "name_keywords_any",
    "source_group_any",
    "article_prefix_any",
)
_FIXTURE_FACT_KEYS = ("name", "brand", "source_group", "article")


def _validate_semantics(rules: tuple[ShadowRule, ...], fixtures: tuple[dict, ...]) -> None:
    """Семантическая валидация v2 (P0.2/P1.1). Собирает ВСЕ ошибки
    проверок 1–8 в один ValueError (сообщения через ``"; "``)."""
    errors: list[str] = []

    # --- правила (проверки 1–4, 6, 8) ---
    seen_predicates: dict[tuple, str] = {}
    for r in rules:
        dims = {d: getattr(r, d) for d in _DIMENSIONS}
        nonempty = {d: v for d, v in dims.items() if v}
        # 0. любое правило (любой tier): ≥1 непустое измерение
        if not nonempty:
            errors.append(f"{r.rule_ref}: правило без непустых измерений")
        # 1. candidate: ≥2 непустых измерения
        if r.tier == TIER_CANDIDATE and len(nonempty) < 2:
            errors.append(
                f"{r.rule_ref}: candidate требует ≥2 непустых измерений "
                f"(найдено {len(nonempty)})"
            )
        # 2. keyword-only (ровно одно измерение и оно keyword) → tier shadow_regression
        if (
            len(nonempty) == 1
            and next(iter(nonempty)) in _KEYWORD_DIMENSIONS
            and r.tier != TIER_SHADOW_REGRESSION
        ):
            errors.append(
                f"{r.rule_ref}: keyword-only правило обязано иметь tier=shadow_regression"
            )
        # 3. candidate derived_from: ≥2 уникальных положительных int
        if r.tier == TIER_CANDIDATE:
            positive = {d for d in r.derived_from if isinstance(d, int) and d > 0}
            if len(positive) < 2:
                errors.append(
                    f"{r.rule_ref}: candidate derived_from требует "
                    "≥2 уникальных положительных int"
                )
        # 4. значения измерений: непусты после normalize, keywords ≥3 символов,
        #    уникальны внутри измерения (после normalize)
        for dim, values in dims.items():
            if len(set(values)) != len(values):
                errors.append(f"{r.rule_ref}: дубли значений в измерении {dim} после normalize")
            for v in values:
                if not v.strip():
                    errors.append(f"{r.rule_ref}: пустое значение в измерении {dim}")
                elif dim in _KEYWORD_DIMENSIONS:
                    kw_tokens = tokenize(v)
                    if not kw_tokens:
                        errors.append(f"{r.rule_ref}: keyword {v!r} пуст после tokenize")
                    elif max(len(t) for t in kw_tokens) < MIN_KEYWORD_LEN:
                        errors.append(
                            f"{r.rule_ref}: keyword {v!r} короче {MIN_KEYWORD_LEN} символов"
                        )
        # 6. дубликаты predicates (одинаковый кортеж нормализованных измерений)
        predicate = tuple(dims[d] for d in _DIMENSIONS)
        if predicate in seen_predicates:
            errors.append(f"{r.rule_ref}: дубликат predicate правила {seen_predicates[predicate]}")
        else:
            seen_predicates[predicate] = r.rule_ref
        # 8. negative_keywords тоже ≥3 символов после normalize
        for k in r.negative_keywords:
            if not tokenize(k) or len(k) < MIN_KEYWORD_LEN:
                errors.append(
                    f"{r.rule_ref}: negative keyword {k!r} короче {MIN_KEYWORD_LEN} символов"
                )

    # --- fixtures (проверки 5, 7) ---
    rule_refs = {r.rule_ref for r in rules}
    refs_with_fixtures = {ref for f in fixtures for ref in f.get("rule_refs", [])}
    for r in rules:
        # 5. у каждого candidate есть ≥1 fixture с его rule_ref в rule_refs
        if r.tier == TIER_CANDIDATE and r.rule_ref not in refs_with_fixtures:
            errors.append(f"{r.rule_ref}: candidate без собственной negative fixture")
    for f in fixtures:
        fref = f.get("fixture_ref", "?")
        # 7. fixture ссылается только на существующие rule_ref; ≥1 непустое поле фактов
        for ref in f.get("rule_refs", []):
            if ref not in rule_refs:
                errors.append(f"fixture {fref}: неизвестный rule_ref {ref}")
        if not any(f.get(k) for k in _FIXTURE_FACT_KEYS):
            errors.append(f"fixture {fref}: нет ни одного непустого поля фактов")

    if errors:
        raise ValueError("; ".join(errors))


@dataclass(frozen=True)
class ProductVerdict:
    product_id: int
    status: str  # prediction | collision | excluded_existing_tool_type | no_match
    option_slug: str = ""
    rule_refs: tuple[str, ...] = ()
    slugs: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


def describe_match(rule: ShadowRule, facts: ProductFacts) -> dict:
    """Деталь матча для evidence: какие измерения/поля/keywords сработали."""
    detail: dict = {"matched": False, "dimensions": [], "keywords": {}, "vetoed_by": ""}
    if rule.negative_keywords:
        for k in rule.negative_keywords:
            if keyword_matches_text(k, facts.original_name) or keyword_matches_text(k, facts.name):
                detail["vetoed_by"] = k
                return detail
    if rule.brand_any:
        if normalize(facts.brand) not in rule.brand_any:
            return detail
        detail["dimensions"].append("brand_any")
    if rule.original_name_keywords_any:
        hits = _keywords_hit(rule.original_name_keywords_any, facts.original_name)
        if not hits:
            return detail
        detail["dimensions"].append("original_name_keywords_any")
        detail["keywords"]["original_name"] = hits
    if rule.name_keywords_any:
        hits = _keywords_hit(rule.name_keywords_any, facts.name)
        if not hits:
            return detail
        detail["dimensions"].append("name_keywords_any")
        detail["keywords"]["name"] = hits
    if rule.source_group_any:
        if normalize(facts.source_group) not in rule.source_group_any:
            return detail
        detail["dimensions"].append("source_group_any")
    if rule.article_prefix_any:
        if not any(normalize(facts.article).startswith(p) for p in rule.article_prefix_any):
            return detail
        detail["dimensions"].append("article_prefix_any")
    detail["matched"] = True
    return detail


def rule_matches(rule: ShadowRule, facts: ProductFacts) -> bool:
    return describe_match(rule, facts)["matched"]


def evaluate_product(rules, facts: ProductFacts) -> ProductVerdict:
    """Вердикт по товару. Existing tool_type исключается ДО матчинга
    (решение 3: перезапись запрещена, попыток быть не должно).
    Prediction наполняет evidence по всем hits (rule_ref → describe_match)."""
    if facts.has_tool_type:
        return ProductVerdict(facts.product_id, "excluded_existing_tool_type")
    hits = [r for r in rules if rule_matches(r, facts)]
    if not hits:
        return ProductVerdict(facts.product_id, "no_match")
    slugs = tuple(sorted({r.option_slug for r in hits}))
    refs = tuple(sorted(r.rule_ref for r in hits))
    if len(slugs) > 1:
        return ProductVerdict(facts.product_id, "collision", slugs=slugs, rule_refs=refs)
    evidence = {r.rule_ref: describe_match(r, facts) for r in hits}
    return ProductVerdict(
        facts.product_id,
        "prediction",
        option_slug=slugs[0],
        rule_refs=refs,
        evidence=evidence,
    )


def validate_against_taxonomy(ruleset: ShadowRuleset, allowed_slugs: set[str]) -> list[str]:
    """Slugs правил, отсутствующие в allowed options (должно быть пусто)."""
    return sorted({r.option_slug for r in ruleset.rules} - allowed_slugs)


def check_negative_fixtures(ruleset: ShadowRuleset) -> list[str]:
    """Rule-scoped проверка: violation, если fixture матчится СВЯЗАННЫМ
    (по ``rule_refs``) правилом; несвязанные правила не проверяются."""
    violations = []
    by_ref = {r.rule_ref: r for r in ruleset.rules}
    for fix in ruleset.negative_fixtures:
        facts = ProductFacts(
            product_id=0,
            name=fix.get("name", ""),
            original_name=fix.get("name", ""),
            brand=fix.get("brand", ""),
            source_group=fix.get("source_group", ""),
            article=fix.get("article", ""),
        )
        for ref in fix.get("rule_refs", []):
            rule = by_ref.get(ref)
            if rule is not None and rule_matches(rule, facts):
                violations.append(
                    f"negative_fixture {fix.get('fixture_ref')!r} "
                    f"({fix.get('name')!r}) матчится правилом {ref}"
                )
    return violations


# --- Corpus (P0.1) ---


@dataclass(frozen=True)
class CorpusItem:
    product_id: int
    change_id: str
    pav_id: int
    source: str
    confidence: int | None
    applied_at: str
    applied_option_slug: str
    name: str = ""
    original_name: str = ""
    brand: str = ""
    source_group: str = ""
    article: str = ""


@dataclass(frozen=True)
class Corpus:
    corpus_id: str
    counters: dict
    items: tuple[CorpusItem, ...]
    expected_recall: float | None

    @property
    def product_ids(self) -> frozenset[int]:
        return frozenset(i.product_id for i in self.items)


_CORPUS_FACTS_KEYS = ("name", "original_name", "brand", "source_group", "article")


@lru_cache(maxsize=1)
def _corpus_validator() -> Draft7Validator:
    schema = json.loads(CORPUS_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, format_checker=FormatChecker())


def load_corpus(path) -> Corpus:
    """Schema + семантика: уникальные product_id, согласованные counters,
    facts_hash == canonical_hash фактов (P0.1)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = sorted(_corpus_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"Corpus не соответствует схеме: {errors[0].message}")
    ids = [i["product_id"] for i in data["items"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Дубли product_id в corpus")
    for i in data["items"]:
        facts = {k: i.get(k, "") for k in _CORPUS_FACTS_KEYS}
        if canonical_hash(facts) != i["facts_hash"]:
            raise ValueError(f"facts_hash не совпадает для product_id={i['product_id']}")
    c = data["counters"]
    if not (c["raw_applied_changes"] >= c["distinct_products"] >= c["current_label_corpus"]):
        raise ValueError("Несогласованные counters")
    if c["current_label_corpus"] != len(data["items"]):
        raise ValueError("current_label_corpus != len(items)")
    items = tuple(
        CorpusItem(
            product_id=i["product_id"],
            change_id=i["change_id"],
            pav_id=i["pav_id"],
            source=i.get("source", ""),
            confidence=i.get("confidence"),
            applied_at=i.get("applied_at", ""),
            applied_option_slug=i["applied_option_slug"],
            name=i.get("name", ""),
            original_name=i.get("original_name", ""),
            brand=i.get("brand", ""),
            source_group=i.get("source_group", ""),
            article=i.get("article", ""),
        )
        for i in data["items"]
    )
    return Corpus(
        corpus_id=data["corpus_id"],
        counters=c,
        items=items,
        expected_recall=data.get("expected_recall"),
    )


# --- Gate-валидаторы sample/labels ---

GATE_LABEL_DECISIONS = frozenset(
    {"correct", "incorrect", "identity_problem", "taxonomy_gap", "unverifiable"}
)


def validate_gate_sample(sample: dict, corpus: Corpus | None) -> list[str]:
    """Аудит sample-артефакта: уникальные IDs, пересечение с corpus = 0,
    обязательные top-level поля и поля строк."""
    violations = []
    required_top = {
        "ruleset_hash",
        "matcher_version",
        "taxonomy_hash",
        "seed",
        "pool",
        "pool_filter_version",
        "rows",
    }
    missing = required_top - set(sample)
    if missing:
        violations.append(f"sample: нет полей {sorted(missing)}")
        return violations
    ids = [r.get("product_id") for r in sample["rows"]]
    if len(ids) != len(set(ids)):
        violations.append("sample: дубли product_id")
    if corpus is not None:
        overlap = sorted(set(ids) & corpus.product_ids)
        if overlap:
            violations.append(f"sample пересекается с training corpus: {overlap[:10]}")
    for r in sample["rows"]:
        for key in ("product_id", "facts_hash", "predicted_option_slug", "rule_refs"):
            if key not in r:
                violations.append(f"sample row без {key}: {r.get('product_id')}")
    return violations


def validate_gate_labels(labels: dict, sample: dict) -> list[str]:
    """Каждая строка sample имеет ровно один label; hash sample совпадает;
    decisions из enum; labels относятся к тому же ruleset/matcher."""
    violations = []
    sample_hash = canonical_hash(sample)
    if labels.get("sample_hash") != sample_hash:
        violations.append("labels.sample_hash != canonical_hash(sample)")
    sample_ids = {r["product_id"] for r in sample["rows"]}
    seen: dict[int, int] = {}
    for lb in labels.get("labels", []):
        pid = lb.get("product_id")
        seen[pid] = seen.get(pid, 0) + 1
        if pid not in sample_ids:
            violations.append(f"label для ID вне sample: {pid}")
        if lb.get("decision") not in GATE_LABEL_DECISIONS:
            violations.append(f"label {pid}: неизвестный decision {lb.get('decision')!r}")
        if not lb.get("reviewer_id") or not lb.get("reviewed_at"):
            violations.append(f"label {pid}: нет reviewer_id/reviewed_at")
    dup = sorted(pid for pid, n in seen.items() if n > 1)
    if dup:
        violations.append(f"дубли labels: {dup[:10]}")
    missing = sorted(sample_ids - set(seen))
    if missing:
        violations.append(f"строки sample без label: {missing[:10]}")
    if labels.get("ruleset_hash") != sample.get("ruleset_hash") or labels.get(
        "matcher_version"
    ) != sample.get("matcher_version"):
        violations.append("labels относятся к другому ruleset/matcher")
    return violations
