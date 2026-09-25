# Phase 6.0 Shadow Rules Engine — Implementation Plan (v2, amended)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Proposal-only shadow rules engine для tool_type: versioned ruleset JSON в репозитории, чистый matcher без единой записи в каталог, read-only shadow-прогоны, versioned gate sample/labels артефакты для ручной проверки precision.

**Architecture:** Чистый модуль `apps/catalog/rules_engine.py` (JSON Schema + semantic validator, tokenizer-based conjunctive matching, collision detection, corpus/sample/labels validators) + read-only management commands `catalog_rules_shadow` и `catalog_rules_gate_validate`. Ruleset — `data/catalog_processing_rules/tool_type.v1.json`; канонический `ruleset_hash` — `processing.canonical_hash`. Поля `rule_ref`/`ruleset_hash` в `CatalogChange` есть — в этом slice они не пишутся (этап 6.1 после gate).

**Tech Stack:** Django 4+/pytest (`DJANGO_SETTINGS_MODULE=config.settings.dev`, `--reuse-db`), `jsonschema==4.23.0`, `apps/catalog/tool_type.py::normalize`, `apps/catalog/queue_contract.py::_allowed_tool_type_options`/`_taxonomy_hash`, `apps/catalog/processing.py::canonical_hash`.

Базовые документы: `2026-07-20-PHASE6_PROPOSAL_SHADOW_PLAN.md` (amended),
ревью `2026-07-21-PHASE6_0_SHADOW_RULES_REVIEW.md` (P0.1–P0.4, P1.1–P1.9).

## Amendment log (v1 → v2)

| Пункт ревью | Суть | Где закрыт |
|---|---|---|
| P0.1 | current-state corpus вместо historical applied | Task 7 + corpus loader/validator (Task 4) |
| P0.2 | semantic constraints candidate rules | Task 4 |
| P0.3 | versioned gate_sample/gate_labels | Task 5 |
| P0.4 | observed precision для gate, per-rule lower bound | docs (основной план), контракт labels (Task 5) |
| P1.1 | rule-scoped negative fixtures | Task 4 |
| P1.2 | раздельные поля + token boundaries | Task 4 |
| P1.3 | analyst-curated mining + derivation report | Task 7 |
| P1.4 | matcher/report versioning | Tasks 4–5 |
| P1.5 | unique atomic output | Task 5 |
| P1.6 | REPEATABLE READ READ ONLY | Task 5 |
| P1.7 | pool contract | Task 5 + основной план |
| P1.8 | полные метрики | Task 5 |
| P1.9 | расширенные тесты | Tasks 4–6 |

## Global Constraints

- **Ноль записей в каталог**: engine и команды не создают/не меняют `Product`, `ProductAttributeValue`, `CatalogChange`, `CatalogProcessingRun/Item`, `ContentFinding`. Единственные файловые записи — JSON-отчёты/артефакты (атомарно, права `0600`).
- Ruleset — versioned JSON в репо; legacy `data/tool_type_rules.json` не перегружать и не менять.
- Candidate rules: ≥2 непустых измерения match; ≥2 уникальных положительных ID в `derived_from`; нормализованные значения непусты (keyword ≥ 3 символов) и уникальны; keyword-only — только tier `shadow_regression`; ≥1 собственная negative fixture на candidate rule; дубликаты predicates — ошибка валидации.
- Negative fixtures — rule-scoped: `fixture_ref`, `rule_refs`, frozen facts, `expected: "no_match"`.
- Title matching: раздельные `original_name_keywords_any` / `name_keywords_any`; токен-семантика (ниже); в evidence — какое поле/keyword сматчили.
- Коллизии: один slug у нескольких правил = одно предсказание со всеми rule_refs; разные slugs = collision/abstention; существующий tool_type = исключение до матчинга; `rewrite_attempts` обязан быть 0.
- Pool contract: `is_active=True`, `content_locked=False`, `Trim(article) != ""`, без PAV tool_type с `value_option IS NOT NULL`; `in-stock` добавляет `available_quantity > 0`. `pool.size` = untyped eligible; typed eligible universe публикуется отдельно; `excluded_existing_tool_type` — его размер, НЕ rewrite attempts.
- Команды НЕ проверяют `FEATURES["catalog_processing"]` (read-only by design).
- Чтение universe — одна транзакция `REPEATABLE READ READ ONLY`; allowed options читаются один раз (validation + taxonomy_hash).
- Отчёт: `report_schema_version`, `matcher_version`, code SHA, `pool_filter_version`, input universe hash, command arguments, start/end; уникальное имя, tmp + `os.replace`, `0600`, отказ от перезаписи без `--force`, SHA-256 файла + канонический hash содержимого.
- Gate: ≥100 predictions вне training corpus; observed precision `correct / all_final_labels >= 99%`; `unverifiable` не исключается из знаменателя молча; per-rule lower bound — только для confidence.
- Confidence в этом slice НЕ присваивается.
- line-length 100 (ruff/black); тесты в `apps/catalog/tests/`; числа пула (190/8403) — baseline observations, не вечные assertions.
- Replay на applied-корпусе — только regression-check (training leakage).
- Merge PR, staging Task 7/8 — только по отдельным авторизациям; Phase 6.1 и auto-apply запрещены.

---

## Completed: Tasks 1–3 (as-built, commits 6c6a039 / 7e97169 / cb781de)

- `apps/catalog/schemas/tool_type_ruleset_v1.json` — JSON Schema v1 (будет расширена в Task 4).
- `apps/catalog/rules_engine.py` — `ShadowRule`/`ShadowRuleset`/`ProductFacts`/`load_ruleset` (Task 1); `ProductVerdict`/`rule_matches`/`evaluate_product`/`validate_against_taxonomy`/`check_negative_fixtures` (Task 2).
- `apps/catalog/management/commands/catalog_rules_shadow.py` — read-only отчёт, deterministic sample, replay (Task 3). As-built отклонение от v1-плана: `excluded_existing_tool_type` считается зеркальным queryset (pool исключает typed-товары до цикла).
- Тесты: `test_rules_engine.py` (13), `test_rules_shadow_command.py` (4). Ревью чистые.

Task 4–6 ниже УСИЛИВАЮТ этот код по ревью; сигнатуры Tasks 1–3 меняются там, где указано явно.

---

### Task 4: Engine strengthening — schema/validator v2, rule-scoped fixtures, token matching, corpus loader

**Files:**
- Modify: `apps/catalog/schemas/tool_type_ruleset_v1.json`
- Create: `apps/catalog/schemas/applied_tool_type_corpus_v1.json`
- Modify: `apps/catalog/rules_engine.py`
- Test: `apps/catalog/tests/test_rules_engine.py` (переработка фикстур + новые тесты)
- Test: `apps/catalog/tests/test_rules_corpus.py` (новый)

**Interfaces:**
- Consumes: Tasks 1–2 код.
- Produces:
  - `MATCHER_VERSION = "1.0"`
  - `tokenize(text: str) -> list[str]`
  - `keyword_matches_text(keyword: str, text: str) -> bool`
  - `ShadowRule` — поля измерений: `brand_any`, `original_name_keywords_any`, `name_keywords_any`, `source_group_any`, `article_prefix_any`, `negative_keywords`, `derived_from` (старое `name_keywords_any` УДАЛЕНО)
  - `load_ruleset(path=None) -> ShadowRuleset` — schema + semantic validation (ValueError со всеми ошибками)
  - `describe_match(rule: ShadowRule, facts: ProductFacts) -> dict`
  - `ProductVerdict(..., evidence: dict = {})`
  - `Corpus`, `CorpusItem`, `load_corpus(path) -> Corpus`
  - `validate_gate_sample(sample: dict, corpus: Corpus | None) -> list[str]`
  - `validate_gate_labels(labels: dict, sample: dict) -> list[str]`

**Семантика токенов (контракт P1.2):** `tokenize` = `normalize` → split по
`[^0-9a-zа-я]+` (после normalize всё в нижнем регистре, ё→е), пустые токены
отброшены. Однословный keyword матчит, если хотя бы один токен текста
**равен keyword или начинается с него** (prefix-покрытие русской морфологии:
«шплинт» матчит «шплинты»). Многословный keyword: токены keyword должны
идти подряд в тексте, все кроме последнего — точно, последний — prefix.
Keyword короче 3 нормализованных символов запрещён semantic validator'ом.

**Semantic validator (P0.2/P1.1), все проверки → ValueError:**
1. candidate: ≥2 непустых измерения;
2. keyword-only (ровно одно измерение и это keyword-измерение) → tier обязан быть `shadow_regression`;
3. candidate `derived_from`: ≥2 уникальных положительных int;
4. значения измерений непусты после normalize; keywords ≥ 3 символов; уникальны внутри измерения (после normalize);
5. у каждого candidate есть ≥1 fixture с его `rule_ref` в `rule_refs`;
6. дубликаты predicates (одинаковый кортеж нормализованных измерений у двух правил) — ошибка;
7. fixture ссылается только на существующие `rule_ref`; ≥1 непустое поле фактов;
8. `negative_keywords` тоже ≥ 3 символов после normalize.

- [ ] **Step 1: Rewrite failing tests**

Переработать `test_rules_engine.py`: базовая фикстура становится валидным
candidate (2 измерения + derived_from + собственная fixture). Старые тесты
matching обновить на раздельные поля. Полный новый набор (имена обязательны):

```python
# фикстура-образец для всех тестов engine v2
def _ruleset_dict(**over):
    data = {
        "version": 1,
        "ruleset_id": "tool_type.v1",
        "rules": [
            {
                "rule_ref": "tt-krep-shplinty-001",
                "option_slug": "krep-shplinty",
                "match": {
                    "source_group_any": ["Крепёж"],
                    "original_name_keywords_any": ["шплинт"],
                },
                "negative_keywords": [],
                "derived_from": [26864, 26865],
            }
        ],
        "negative_fixtures": [
            {
                "fixture_ref": "nf-shplinty-001",
                "rule_refs": ["tt-krep-shplinty-001"],
                "name": "Гвоздь строительный 6х100",
                "source_group": "Крепёж",
            }
        ],
    }
    data.update(over)
    return data
```

Тесты (Task 4):
- `test_load_ruleset_valid` — candidate из фикстуры проходит; tier default candidate; hash 64.
- `test_candidate_requires_two_dimensions` — одно измерение → ValueError.
- `test_keyword_only_must_be_regression_tier` — keyword-only + tier candidate → ValueError; то же с `shadow_regression` → OK.
- `test_candidate_requires_two_derived_from` — `[26864]` → ValueError; дубликаты `[26864, 26864]` → ValueError.
- `test_dimension_values_normalized_unique` — `["Шплинт", "шплинт"]` → ValueError.
- `test_keyword_min_length` — keyword `"оч"` → ValueError.
- `test_empty_after_tokenize_rejected` — keyword `"!!!"` → ValueError.
- `test_candidate_requires_own_fixture` — fixture без rule_ref правила → ValueError.
- `test_fixture_unknown_rule_ref` — ValueError.
- `test_duplicate_predicates_rejected` — два правила с одинаковыми измерениями → ValueError.
- `test_schema_violation_still_rejected` / `test_duplicate_rule_ref_rejected` — сохранить.
- `test_ruleset_hash_stable_under_key_reorder` — сохранить.
- `test_tokenize_separators` — `"Шплинт 6,4х76 (DIN 94)"` → `["шплинт", "6", "4х76", "din", "94"]`.
- `test_keyword_prefix_matches_morphology` — «шплинт» матчит «Шплинты 6,4х76».
- `test_keyword_no_substring_match` — «болгарка» НЕ матчит «Гайка болгарская М8».
- `test_phrase_keyword_consecutive` — «ключ динамометрический» матчит «Ключ динамометрический 1/2»; НЕ матчит «динамометрический ключ» (порядок).
- `test_field_separation` — keyword в `original_name_keywords_any` НЕ матчит, если слово только в `name`; и наоборот.
- `test_match_evidence_records_field` — `describe_match` возвращает поле и keyword.
- `test_brand_and_negative_veto` — сохранить семантику Task 2 (обновить поля).
- `test_evaluate_excludes_existing_tool_type` / `test_same_slug_multi_rule` / `test_collision` — сохранить, обновить фикстуры; у prediction проверить `evidence` непустой.
- `test_validate_against_taxonomy` — сохранить.
- `test_check_negative_fixtures_scoped` — fixture запрещает match ТОЛЬКО связанных правил; правило вне `rule_refs` может матчить fixture без violation.

`test_rules_corpus.py` (новый):
- `test_load_corpus_valid` — валидный corpus (2 items) грузится; счётчики согласованы.
- `test_corpus_duplicate_product_id_rejected`.
- `test_corpus_facts_hash_mismatch_rejected`.
- `test_corpus_counters_inconsistent_rejected` — `distinct_products > raw_applied_changes` → ValueError.
- `test_validate_gate_sample_excludes_corpus` — sample с product_id из corpus → violation.
- `test_validate_gate_sample_unique_ids`.
- `test_validate_gate_labels_complete` — все rows покрыты, hash sample совпадает → [].
- `test_validate_gate_labels_missing_label` / `test_wrong_sample_hash` / `test_unknown_decision`.

- [ ] **Step 2: Run to verify RED**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_rules_engine.py apps/catalog/tests/test_rules_corpus.py -x -q`
Expected: FAIL (schema/поля отсутствуют).

- [ ] **Step 3: Implement engine v2**

Schema `tool_type_ruleset_v1.json` (изменения): в `rule.match` свойства
`brand_any`, `original_name_keywords_any`, `name_keywords_any`,
`source_group_any`, `article_prefix_any` (старое `name_keywords_any`
удалено); `negative_fixture`: required `["fixture_ref", "rule_refs"]`,
свойства `fixture_ref` (pattern `^[a-z0-9][a-z0-9-]*$`, maxLength 64),
`rule_refs` (array, minItems 1, items pattern rule_ref), `expected`
(enum `["no_match"]`, default), `name`/`brand`/`source_group`/`article`/`note`.

Новый файл `apps/catalog/schemas/applied_tool_type_corpus_v1.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "applied tool_type corpus v1 (current-state, P0.1)",
  "type": "object",
  "required": ["version", "corpus_id", "counters", "items"],
  "additionalProperties": false,
  "properties": {
    "version": {"type": "integer", "const": 1},
    "corpus_id": {"type": "string", "minLength": 1},
    "extracted_at": {"type": "string"},
    "source": {"type": "string"},
    "expected_recall": {"type": "number", "minimum": 0, "maximum": 1},
    "counters": {
      "type": "object",
      "required": ["raw_applied_changes", "distinct_products", "current_label_corpus", "historical_label_collisions"],
      "additionalProperties": false,
      "properties": {
        "raw_applied_changes": {"type": "integer", "minimum": 0},
        "distinct_products": {"type": "integer", "minimum": 0},
        "current_label_corpus": {"type": "integer", "minimum": 0},
        "historical_label_collisions": {"type": "integer", "minimum": 0}
      }
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["product_id", "change_id", "pav_id", "applied_option_slug", "facts_hash"],
        "additionalProperties": false,
        "properties": {
          "product_id": {"type": "integer", "exclusiveMinimum": 0},
          "change_id": {"type": "string", "minLength": 1},
          "pav_id": {"type": "integer", "exclusiveMinimum": 0},
          "source": {"type": "string"},
          "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
          "applied_at": {"type": "string"},
          "applied_option_slug": {"type": "string", "minLength": 1},
          "name": {"type": "string", "default": ""},
          "original_name": {"type": "string", "default": ""},
          "brand": {"type": "string", "default": ""},
          "source_group": {"type": "string", "default": ""},
          "article": {"type": "string", "default": ""},
          "facts_hash": {"type": "string", "minLength": 64, "maxLength": 64}
        }
      }
    }
  }
}
```

Engine (ключевой новый код; остальное сохранить из Tasks 1–2, обновив поля):

```python
import re

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
        if all(w == k for w, k in zip(window[:-1], kw_tokens[:-1])) and (
            window[-1] == kw_tokens[-1] or window[-1].startswith(kw_tokens[-1])
        ):
            return True
    return False


def _keywords_hit(keywords: tuple[str, ...], text: str) -> list[str]:
    return [k for k in keywords if keyword_matches_text(k, text)]


def describe_match(rule: ShadowRule, facts: ProductFacts) -> dict:
    """Деталь матча для evidence: какие измерения/поля/keywords сработали."""
    detail: dict = {"matched": False, "dimensions": [], "keywords": {}, "vetoed_by": ""}
    if rule.negative_keywords:
        for k in rule.negative_keywords:
            if keyword_matches_text(k, facts.original_name) or keyword_matches_text(
                k, facts.name
            ):
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
```

`evaluate_product`: prediction verdict наполняет `evidence={rule_ref: describe_match(...)}` по всем hits. `check_negative_fixtures(ruleset)`: для каждой fixture — violation, если связанное правило (по `rule_refs`) матчит её facts; несвязанные правила не проверяются.

`load_ruleset` после schema validation вызывает `_validate_semantics(rules, fixtures)`, собирающий ВСЕ ошибки пунктов 1–8 в один ValueError (сообщения через `"; "`).

```python
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
    items = tuple(CorpusItem(**{k: i.get(k) for k in CorpusItem.__dataclass_fields__ if k in i} | {k: i.get(k, "") for k in _CORPUS_FACTS_KEYS}) for i in data["items"])
    return Corpus(
        corpus_id=data["corpus_id"],
        counters=c,
        items=items,
        expected_recall=data.get("expected_recall"),
    )
```

(реализацию CorpusItem-сборки упростить явным конструктором по полям; код выше — ориентир, не verbatim).

Gate validators:

```python
GATE_LABEL_DECISIONS = frozenset(
    {"correct", "incorrect", "identity_problem", "taxonomy_gap", "unverifiable"}
)


def validate_gate_sample(sample: dict, corpus: Corpus | None) -> list[str]:
    """Аудит sample-артефакта: уникальные IDs, пересечение с corpus = 0,
    обязательные top-level поля и поля строк."""
    violations = []
    required_top = {
        "ruleset_hash", "matcher_version", "taxonomy_hash",
        "seed", "pool", "pool_filter_version", "rows",
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
```

`ShadowRuleset` дополнить `matcher_version: str = MATCHER_VERSION`.

- [ ] **Step 4: Run to verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_rules_engine.py apps/catalog/tests/test_rules_corpus.py -q`
Expected: все зелёные; затем `pytest apps/catalog -q` — весь suite (командные тесты Task 3 будут обновлены в Task 5; если падают из-за старых полей — обновить их фикстуры в ЭТОМ task минимально, отметив в отчёте).

- [ ] **Step 5: Commit**

```bash
git add apps/catalog/schemas/tool_type_ruleset_v1.json apps/catalog/schemas/applied_tool_type_corpus_v1.json apps/catalog/rules_engine.py apps/catalog/tests/test_rules_engine.py apps/catalog/tests/test_rules_corpus.py apps/catalog/tests/test_rules_shadow_command.py
git commit -m "feat(catalog): semantic validator, rule-scoped fixtures, token matching, corpus loader (Phase 6.0 review P0.2/P1.1/P1.2)"
```

---

### Task 5: Command strengthening — snapshot read, versioning, atomic output, метрики, gate artifacts

**Files:**
- Modify: `apps/catalog/management/commands/catalog_rules_shadow.py`
- Create: `apps/catalog/management/commands/catalog_rules_gate_validate.py`
- Test: `apps/catalog/tests/test_rules_shadow_command.py` (переработка + новые)
- Test: `apps/catalog/tests/test_rules_snapshot.py` (новый, TransactionTestCase)

**Interfaces:**
- Consumes: Task 4 (`MATCHER_VERSION`, `load_corpus`, `validate_gate_sample`, `validate_gate_labels`, `describe_match`).
- Produces:
  - CLI `catalog_rules_shadow [--pool in-stock|all] [--ruleset PATH] [--sample-size N] [--seed N] [--replay-corpus PATH] [--out PATH] [--force] [--gate-sample-out PATH] [--corpus PATH]`
  - CLI `catalog_rules_gate_validate --gate-sample PATH --labels PATH`
  - Report v1.0 (поля ниже); gate_sample artifact v1.

**Report v1.0 (`report_schema_version: "1.0"`):**
- `report_schema_version`, `matcher_version`, `code_sha` (`git rev-parse HEAD`, fallback `"unknown"`), `pool_filter_version: "1.0"`, `ruleset_id`, `ruleset_hash`, `taxonomy_hash`;
- `command`: {"name": "catalog_rules_shadow", "args": {...}};
- `started_at`, `finished_at`, `duration_seconds`, `snapshot_isolation` (фактический режим: `repeatable_read_read_only` или `default_deferred` с причиной);
- `input_universe_hash` — `canonical_hash({"pool": pool, "untyped_ids": sorted ids, "typed_eligible": n})`;
- `pool`: {"name", "size" (untyped eligible), "typed_eligible_universe", "excluded_existing_tool_type", "rewrite_attempts": 0};
- `counts`: predictions, collisions, no_match, excluded_existing_tool_type, regression_tier_hits, regression_tier_collisions;
- `per_rule`: {rule_ref: {"tier", "raw_hits", "prediction_hits", "collision_hits", "same_slug_multi_hits", "coverage_share"}} (coverage_share = prediction_hits / pool.size, round 4);
- `predictions_share` = predictions / pool.size;
- `collisions`, `predictions` (с evidence: facts + `facts_hash` + match detail), `sample` (seed/size/product_ids).

**gate_sample artifact (`--gate-sample-out`, версия 1):**
```json
{
  "version": 1,
  "artifact": "gate_sample",
  "ruleset_hash": "...", "matcher_version": "1.0", "taxonomy_hash": "...",
  "seed": 20260721, "pool": "in-stock", "pool_filter_version": "1.0",
  "rows": [
    {"product_id": 1, "name": "", "original_name": "", "brand": "",
     "source_group": "", "article": "", "facts_hash": "...",
     "predicted_option_slug": "...", "rule_refs": ["..."]}
  ]
}
```
Перед записью — `validate_gate_sample(artifact, corpus)` (corpus из `--corpus`, если задан); violations → CommandError.

**Atomic output (P1.5):** default имя `rules_shadow_{pool}_{YYYYMMDDTHHMMSSZ}_{ruleset_hash[:12]}.json` в `var/catalog-processing/shadow/`; существующий `--out` без `--force` → CommandError; запись через tmp-файл в той же директории + `os.replace`; `os.chmod(path, 0o600)` когда `os.name == "posix"`; stdout печатает sha256 файла и `content_hash` = `canonical_hash(report без volatile: generated_at/started_at/finished_at/duration_seconds)`.

**Snapshot read (P1.6):**
```python
from django.db import connection, transaction

SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"

# в handle: всё чтение в одном блоке
isolation = "default_deferred"
with transaction.atomic():
    try:
        with connection.cursor() as cur:
            cur.execute(SNAPSHOT_SQL)
        isolation = "repeatable_read_read_only"
    except Exception as exc:  # тест-окружение внутри внешней транзакции
        isolation = f"default_deferred:{type(exc).__name__}"
    options_list = _allowed_tool_type_options()  # один раз
    ... все queryset/итерации здесь ...
```
`SET TRANSACTION` выполняется до первого SELECT в транзакции; в pytest-окружении (внешняя транзакция) деградация фиксируется в `snapshot_isolation`.

**Pool (P1.7):**
```python
from django.db.models import Exists, OuterRef
from django.db.models.functions import Trim

def _eligible_qs(*, has_tool_type: bool):
    has_tt = ProductAttributeValue.objects.filter(
        product_id=OuterRef("pk"), attribute__slug="tool_type", value_option__isnull=False
    )
    return (
        Product.objects.annotate(_has_tt=Exists(has_tt), _art=Trim("article"))
        .filter(_has_tt=has_tool_type, is_active=True, content_locked=False)
        .exclude(_art="")
    )

def _pool_queryset(pool: str, *, has_tool_type: bool = False):
    qs = _eligible_qs(has_tool_type=has_tool_type)
    if pool == "in-stock":
        qs = qs.filter(available_quantity__gt=0)
    return qs.order_by("pk")
```

**`catalog_rules_gate_validate`:** читает оба файла, `validate_gate_labels(labels, sample)`; violations → CommandError со списком; печатает сводку decisions (correct/incorrect/... counts, observed precision = correct / rows с финальными labels — `correct|incorrect` в числителе `correct`, знаменатель = все rows) и `gate_passed = precision >= 0.99 and rows >= 100 and collisions == 0` (collisions берётся из sample-отчёта, если поле есть; иначе только precision+rows). Никаких записей.

- [ ] **Step 1: Rewrite failing tests**

Обновить `test_rules_shadow_command.py` под v1.0 (фикстуры candidate-правил из Task 4) + новые тесты:
- `test_report_versioning_fields` — все поля versioning присутствуют; `rewrite_attempts == 0`; `snapshot_isolation` непустой.
- `test_typed_eligible_universe_published` — typed товар учтён в `typed_eligible_universe`/`excluded_existing_tool_type`, не в `pool.size`.
- `test_whitespace_article_excluded` — article `"   "` вне пула.
- `test_inactive_locked_out_of_stock_excluded` — три товара отфильтрованы, видны в `all`-pool только частично: inactive/locked исключены из обоих пулов; out-of-stock исключён из in-stock, присутствует в `all`.
- `test_pool_all_vs_in_stock`.
- `test_unique_default_filename_no_overwrite` — два прогона без `--out` → два разных файла, оба существуют.
- `test_out_exists_requires_force` — повторный `--out` без `--force` → CommandError; с `--force` → OK.
- `test_output_file_mode_0600` — `@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")`.
- `test_collision_fully_reported` — два правила разных slugs на один товар → predictions=0, collisions=1, per_rule collision_hits по обоим.
- `test_per_rule_metrics` — raw/prediction/collision hits и coverage_share.
- `test_gate_sample_artifact` — `--gate-sample-out` + `--corpus`: rows с frozen facts/facts_hash; `validate_gate_sample` чист.
- `test_gate_sample_corpus_overlap_rejected` — corpus содержит товар из пула → CommandError. (corpus product дать tool_type PAV нельзя — тогда он вне untyped pool; тест: corpus item c product_id товара, который в пуле — overlap ловится по ID.)
- `test_zero_writes_including_content_findings` — counts Product/PAV/CatalogChange/Run/Item/ContentFinding неизменны.
- `test_replay_regression_not_gate` — replay-секция считает recall, не валит команду при mismatches.

`test_rules_snapshot.py` (TransactionTestCase, механизм изоляции):
- `test_repeatable_read_holds_snapshot` — вручную: `transaction.atomic()` + SET TRANSACTION; count; в другом соединении вставка товара; повторный count равен первому.

`test_rules_gate_validate.py`:
- `test_valid_labels_pass` — выход 0, сводка decisions.
- `test_missing_label_fails`, `test_unknown_decision_fails`, `test_wrong_sample_hash_fails`.

- [ ] **Step 2: Run RED** — как в Task 4.
- [ ] **Step 3: Implement** — по спецификации выше; `code_sha` через `subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)` с fallback `"unknown"`.
- [ ] **Step 4: Run GREEN** — новые тесты + весь `apps/catalog`.
- [ ] **Step 5: Commit**

```bash
git add apps/catalog/management/commands/catalog_rules_shadow.py apps/catalog/management/commands/catalog_rules_gate_validate.py apps/catalog/tests/test_rules_shadow_command.py apps/catalog/tests/test_rules_snapshot.py apps/catalog/tests/test_rules_gate_validate.py
git commit -m "feat(catalog): snapshot read, report versioning, atomic output, gate artifacts (Phase 6.0 review P0.3/P1.4-P1.8)"
```

### Task 6: Coverage sweep + Step-3 verification

**Files:**
- Test: `apps/catalog/tests/test_rules_engine.py`, `test_rules_shadow_command.py` (добивка пробелов)

- [ ] **Step 1: Добить тесты из P1.9, не закрытые Tasks 4–5:** invalid JSON file; missing file; пустой ruleset (`"rules": []` — валиден, 0 predictions); sample исключает training corpus (уже в Task 5 — проверить дубли); отчёт deterministic кроме volatile-полей (два прогона → равный content_hash).
- [ ] **Step 2: Полная проверка (обязательная батарея ревью Шаг 3):**

```powershell
.\.venv\Scripts\python.exe -m pytest apps/catalog/tests/test_rules_engine.py apps/catalog/tests/test_rules_shadow_command.py apps/catalog/tests/test_rules_corpus.py apps/catalog/tests/test_rules_gate_validate.py -q
.\.venv\Scripts\python.exe -m pytest apps/catalog -q
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check apps/catalog
.\.venv\Scripts\python.exe -m black --check apps/catalog
```

- [ ] **Step 3: Commit** `test(catalog): Phase 6.0 review coverage sweep (P1.9)` — только изменённые тестовые файлы.

### Task 7 (STOP-GATE, отдельная staging-авторизация): current-state corpus → ruleset v1

**Files:**
- Create: `data/catalog_processing_rules/tool_type.v1.json`
- Create: `data/catalog_processing_rules/applied_corpus_tool_type.v1.json`
- Create: `docs/catalog/phase6-ruleset-v1-derivation.md`
- Test: `apps/catalog/tests/test_rules_corpus_replay.py`

**P0.1 extraction (staging, read-only):**

```python
# manage.py shell, read-only
import json
from apps.catalog.models import CatalogChange, ProductAttributeValue

applied = (
    CatalogChange.objects.filter(status="applied", target_kind="tool_type")
    .order_by("product_ref", "applied_at")
    .select_related("item__product")
)
by_product = {}
for ch in applied:
    by_product.setdefault(ch.product_ref, []).append(ch)

items, collisions = [], 0
for pid, changes in by_product.items():
    pav = (
        ProductAttributeValue.objects.filter(
            product_id=pid, attribute__slug="tool_type", value_option__isnull=False
        )
        .select_related("value_option", "product")
        .first()
    )
    if pav is None:
        continue  # текущего label нет — товар исключается, фиксируется отдельно
    slug = pav.value_option.slug
    if any((c.after_value or {}).get("option_slug", slug) != slug for c in changes):
        collisions += 1
    current = next(
        (
            c
            for c in reversed(changes)
            if (c.after_value or {}).get("option_slug") == slug
        ),
        None,
    )
    if current is None:
        continue  # нет provenance под текущий label — фиксируется отдельно
    p = pav.product
    items.append({
        "product_id": pid,
        "change_id": str(current.pk),
        "pav_id": pav.pk,
        "source": pav.source,
        "confidence": pav.confidence,
        "applied_at": current.applied_at.isoformat() if current.applied_at else "",
        "applied_option_slug": slug,
        "name": p.name or "", "original_name": p.original_name or "",
        "brand": p.brand or "", "source_group": p.source_group or "",
        "article": p.article or "",
    })
counters = {
    "raw_applied_changes": sum(len(v) for v in by_product.values()),
    "distinct_products": len(by_product),
    "current_label_corpus": len(items),
    "historical_label_collisions": collisions,
}
```

`facts_hash` для каждой строки считается `canonical_hash` по 5 фактам при
формировании файла (локально, после выгрузки). Ожидания baseline: raw=56,
distinct=54, corpus=54, collisions=2 — **перепроверить свежим SELECT**,
расхождение зафиксировать в derivation report.

**Деривация (P1.3, analyst-curated):** для каждого candidate rule в
`docs/catalog/phase6-ruleset-v1-derivation.md` — обоснование: группа
товаров, общие измерения (≥2), почему slug, negative fixture и её источник.
Human review каждого правила — отдельным подтверждением пользователя до
коммита ruleset.

**Replay regression (НЕ gate):** `test_rules_corpus_replay.py` —
`recall >= expected_recall` по candidate tier; taxonomy check
`validate_against_taxonomy == []`; каждая candidate rule имеет fixture
(покрыто loader'ом).

### Task 8 (STOP-GATE, отдельная staging-авторизация): shadow run + gate sample

1. После merge и deploy: staging SHA = dev, `/healthz/` 200, flag False.
2. Read-only прогоны: `--pool in-stock --sample-size 100 --seed 20260721 --corpus data/catalog_processing_rules/applied_corpus_tool_type.v1.json --gate-sample-out /app/logs/gate_sample_instock.json` и `--pool all` аналогично; replay с `--replay-corpus`.
3. Pre/post invariants: counts CatalogChange/PAV(=60 896 baseline, сверить свежим)/Product/ContentFinding неизменны; старые runs неизменны; flag False; healthz 200.
4. Артефакты (отчёты + gate_sample, sha256 каждого) — в отчёт пользователю.
5. Если predictions < 100 — зафиксировать дефицит (накопление по прогонам допускается), правила ad-hoc не расширять.
6. Ручная разметка `gate_labels.json` — отдельный этап за пользователем; validator `catalog_rules_gate_validate` считает observed precision.
7. STOP: Phase 6.1, новые runs, auto-apply — запрещены.

## Self-Review

- Spec coverage: P0.1→Task 7+loader(Task 4); P0.2→Task 4; P0.3→Task 5; P0.4→docs+gate_validate(Task 5); P1.1/P1.2→Task 4; P1.3→Task 7; P1.4/P1.5/P1.6/P1.7/P1.8→Task 5; P1.9→Tasks 4–6.
- Placeholder scan: правила ruleset — analyst-curated выход Task 7 с derivation report (не placeholder, а задокументированный процесс); `expected_recall` измеряется replay.
- Type consistency: `CorpusItem`/`validate_gate_*`/`describe_match` согласованы между Tasks 4–5; старое поле `name_keywords_any` удалено везде (Tasks 4–5 обновляют все фикстуры).
- Известные компромиссы: concurrency-тест изоляции проверяет механизм SQL, не гонку в команде; на Windows режим `0600` не проверяется (skipif, покрыто в CI Linux).
