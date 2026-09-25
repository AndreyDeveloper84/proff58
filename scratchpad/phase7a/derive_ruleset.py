# Task 6 / Stage 6 — analyst-curated derivation draft ruleset tool_type.v1.
# Строит draft ruleset из 11 multi-product label-семейств corpus, пишет
# scratchpad/phase7a/tool_type.v1.json и прогоняет ВСЕ локальные проверки
# плана (Step 3): load_ruleset (schema+семантика), check_negative_fixtures,
# derived_from ⊆ corpus, replay через продакшн-логику Command._replay,
# per-rule hits, rule-коллизии и wrong-slug predictions на corpus.
# source_group/name берутся из corpus по product_id (без ручного набора
# кириллицы — исключает опечатки в измерениях и fixtures).
import json
import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.management.commands.catalog_rules_shadow import Command as ShadowCommand
from apps.catalog.rules_engine import (
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_corpus,
    load_ruleset,
)

CORPUS = Path("scratchpad/phase7a/applied_corpus_tool_type.v1.json")
OUT = Path("scratchpad/phase7a/tool_type.v1.json")
RESULT = Path("scratchpad/phase7a/derive_result.json")

doc = json.loads(CORPUS.read_text(encoding="utf-8"))
items = {i["product_id"]: i for i in doc["items"]}


def sg(pid):
    return items[pid]["source_group"]


def on(pid):
    return items[pid]["original_name"]


def art(pid):
    return items[pid]["article"]


# name vs original_name расхождения (для derivation doc)
name_diff = sorted(pid for pid, i in items.items() if (i["name"] or "") != (i["original_name"] or ""))

# --- 11 candidate-правил: (rule_ref, slug, pids, keywords, note) ---
RULES = [
    ("tt-krep-shplinty-nabor", "krep-shplinty", [26863, 26864, 26865], ["шплинт"],
     "Наборы шплинтов в sg=Оснастка; prefix 'шплинт' покрывает 'шплинтов'."),
    ("tt-puskovye-provoda-startovye", "puskovye-provoda", [27250, 27251, 27254],
     ["провода стартовые"],
     "Пусковые (стартовые) провода в sg=Оснастка; двухсловный keyword."),
    ("tt-bp-pnevmosteplery-gvozde", "bp-pnevmosteplery", [28891, 28892, 28893, 28901],
     ["пневмонейлер", "гвоздезабивной"],
     "Пневмонейлеры (3) + гвоздезабивной пневмопистолет (1) в sg=Пневмоинструмент."),
    ("tt-siz-ochki-zashchitnye", "siz-ochki", [36300, 36302, 36304, 36377, 36378],
     ["маска щиток", "очки защитные"],
     "Защитные маски-щитки (3) + очки газосварщика (2) в sg=СИЗ."),
    ("tt-dinamometricheskie-klyuchi-klyuch", "dinamometricheskie-klyuchi", [12957, 12959],
     ["ключ динамометрический"],
     "ADR-0011 remediation family; 'ключ динамометрический' НЕ матчит "
     "'отвертка динамометрическая' (13936) и 'адаптер динамометрический' (10537)."),
    ("tt-adaptery-universal", "adaptery", [1110, 1111, 6681, 6682, 10537],
     ["адаптер"],
     "Адаптеры в трёх sg (Аккумуляторы и зарядные устройства, Запасные части, "
     "Измерительный инструмент); hyphen split: 'адаптер-переходник' -> токен 'адаптер'."),
    ("tt-izm-shtativy-derzhatel", "izm-shtativy", [10631, 10632], ["держатель"],
     "Держатели KRAFTOOL в sg=Измерительный инструмент (provenance = applied changes)."),
    ("tt-svar-reduktory-regulyator", "svar-reduktory", [31106, 31109],
     ["регулятор расхода газа"],
     "Регуляторы расхода газа в sg=Сварочное оборудование; трёхсловный keyword."),
    ("tt-hoz-lenty-malyarnaya", "hoz-lenty", [37269, 37270], ["лента малярная"],
     "Малярные ленты в sg=Строительно-отделочный инструмент."),
    ("tt-nabory-instrumenta-dielektr", "nabory-instrumenta", [22650, 22651],
     ["набор диэлектрического"],
     "Диэлектрические наборы в sg=Наборы инструмента; отличает от 'набор медных шайб'."),
    # Review Stage 7 (2026-07-21): исходное правило [сумка,кейс]x[Бензоинструмент,
    # Прочее] REJECTED — неподтверждённые cross-комбинации. Оставлена только
    # подтверждённая пара кейс+Прочее; 1855 (сумка) возвращён в синглтоны.
    ("tt-yashchiki-sumki-keys-prochee", "yashchiki-sumki", [30223, 30225],
     ["кейс"],
     "Кейсы Hitachi в sg=Прочее (review: cross-product отклонён; 1855 'сумка' "
     "исключён из области правила до второго подтверждения)."),
]

rules = []
for ref, slug, pids, kws, note in RULES:
    sgs = sorted({sg(p) for p in pids})
    rules.append({
        "rule_ref": ref,
        "option_slug": slug,
        "tier": "candidate",
        "match": {
            "original_name_keywords_any": kws,
            "source_group_any": sgs,
        },
        "derived_from": sorted(pids),
        "note": note,
    })

# --- negative fixtures из реальных соседних товаров corpus ---
FIXTURES = [
    ("fix-puskovye-27250", ["tt-krep-shplinty-nabor"], 27250,
     "sg=Оснастка без 'шплинт': пусковые провода — соседний label той же группы."),
    ("fix-shplinty-26863", ["tt-puskovye-provoda-startovye"], 26863,
     "sg=Оснастка без 'провода стартовые': набор шплинтов."),
    ("fix-pnevmomolotok-28677", ["tt-bp-pnevmosteplery-gvozde"], 28677,
     "sg=Пневмоинструмент: оснастка отбойного молотка, не степлер."),
    ("fix-poyas-36713", ["tt-siz-ochki-zashchitnye"], 36713,
     "sg=СИЗ: пояс монтажника, не очки/маска."),
    ("fix-otvertka-13936", ["tt-dinamometricheskie-klyuchi-klyuch"], 13936,
     "ADR-0011 near-miss: отвертка динамометрическая в той же sg — НЕ ключ."),
    ("fix-adapter-dinam-10537", ["tt-dinamometricheskie-klyuchi-klyuch", "tt-izm-shtativy-derzhatel"],
     10537, "Адаптер динамометрический: другая sg и без 'держатель'."),
    ("fix-derzhatel-10631", ["tt-adaptery-universal"], 10631,
     "sg=Измерительный инструмент без 'адаптер': держатель."),
    ("fix-klemmy-30870", ["tt-svar-reduktory-regulyator"], 30870,
     "sg=Сварочное оборудование: кабель с клеммой, не регулятор."),
    ("fix-plitkorez-37594", ["tt-hoz-lenty-malyarnaya"], 37594,
     "sg=Строительно-отделочный: плиткорез, не лента."),
    ("fix-shaiby-23255", ["tt-nabory-instrumenta-dielektr"], 23255,
     "sg=Наборы инструмента: 'набор медных шайб' — разделяет keyword 'набор'."),
    ("fix-svechi-1817", ["tt-yashchiki-sumki-keys-prochee"], 1817,
     "sg=Бензоинструмент (вне области правила): свеча, не кейс."),
    ("fix-sumka-1855", ["tt-yashchiki-sumki-keys-prochee"], 1855,
     "Отклонённая review cross-комбинация: 'сумка' в sg=Бензоинструмент "
     "НЕ должна матчиться суженным правилом."),
]

fixtures = []
for fref, refs, pid, note in FIXTURES:
    fixtures.append({
        "fixture_ref": fref,
        "rule_refs": refs,
        "name": on(pid),
        "source_group": sg(pid),
        "article": art(pid),
        "note": f"product_id={pid}; {note}",
    })

ruleset_doc = {
    "version": 1,
    "ruleset_id": "tool_type.v1",
    "note": "draft, pending human approval 2026-07-21",
    "rules": rules,
    "negative_fixtures": fixtures,
}
OUT.write_text(json.dumps(ruleset_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
               encoding="utf-8")

# --- проверки плана Task 6 Step 3 ---
result = {"ruleset_path": str(OUT), "name_diff_pids": name_diff, "checks": {}}

rs = load_ruleset(OUT)  # schema + семантика (P0.2)
result["ruleset_hash"] = rs.ruleset_hash
result["rules_count"] = len(rs.rules)
result["checks"]["load_ruleset"] = "OK"

fix_violations = check_negative_fixtures(rs)
result["checks"]["check_negative_fixtures"] = fix_violations
assert fix_violations == [], fix_violations

corpus = load_corpus(CORPUS)
ids = {i.product_id for i in corpus.items}
bad = [r.rule_ref for r in rs.rules if not set(r.derived_from) <= ids]
result["checks"]["derived_from_subset"] = "OK" if not bad else bad
assert not bad, f"leakage: {bad}"

# replay через продакшн-логику (та же, что Command._replay)
candidate_rules = [r for r in rs.rules if r.tier == "candidate"]
replay = ShadowCommand._replay(rs, CORPUS)
result["replay"] = replay

# Разведение двух хэшей corpus (review Stage 7, находка 5): replay
# эмитирует ``corpus_hash`` = canonical_hash(полного dict, ВКЛЮЧАЯ volatile
# extracted_at) — это loader_corpus_hash, fingerprint конкретного файла;
# стабильный artifact_content_hash считается extraction'ом БЕЗ extracted_at
# и является источником corpus_id.
result["hash_registry"] = {
    "artifact_content_hash": {
        "value": doc.get("corpus_hash") or "81c15c5fbcb94c61c0ec2ff9dce7c14d42f5325c9068756c6e32bef69e37361d",
        "algorithm": "canonical_hash(doc БЕЗ extracted_at); источник corpus_id; стабилен между прогонами",
        "computed_by": "scratchpad/phase7a/extract_corpus.py (extraction)",
    },
    "loader_corpus_hash": {
        "value": replay["corpus_hash"],
        "algorithm": "canonical_hash(полный dict ВКЛЮЧАЯ extracted_at); volatile между прогонами",
        "computed_by": "Command._replay (apps/catalog/management/commands/catalog_rules_shadow.py)",
    },
}

# per-rule hits + wrong-slug + collisions на corpus
per_rule = {r.rule_ref: [] for r in candidate_rules}
wrong, collisions, no_match = [], [], []
for item in corpus.items:
    facts = ProductFacts(
        product_id=item.product_id,
        name=item.name,
        original_name=item.original_name,
        brand=item.brand,
        source_group=item.source_group,
        article=item.article,
    )
    verdict = evaluate_product(candidate_rules, facts)
    for ref in verdict.rule_refs:
        per_rule[ref].append(item.product_id)
    if verdict.status == "collision":
        collisions.append({"product_id": item.product_id, "slugs": list(verdict.slugs)})
    elif verdict.status == "prediction" and verdict.option_slug != item.applied_option_slug:
        wrong.append({"product_id": item.product_id, "expected": item.applied_option_slug,
                      "predicted": verdict.option_slug})
    elif verdict.status == "no_match":
        no_match.append(item.product_id)

result["per_rule_hits"] = {k: sorted(v) for k, v in sorted(per_rule.items())}
result["rule_collisions_on_corpus"] = collisions
result["wrong_slug_predictions"] = wrong
result["no_match_pids"] = sorted(no_match)
result["no_match_count"] = len(no_match)

# каждое правило матчит ровно свои derived_from внутри corpus?
overfit_exact, extra_hits = [], {}
for r in candidate_rules:
    hits = set(per_rule[r.rule_ref])
    derived = set(r.derived_from)
    if hits == derived:
        overfit_exact.append(r.rule_ref)
    else:
        extra_hits[r.rule_ref] = {"derived_not_hit": sorted(derived - hits),
                                  "hit_not_derived": sorted(hits - derived)}
result["rules_hits_eq_derived"] = overfit_exact
result["rules_hits_delta"] = extra_hits

RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                  encoding="utf-8")

print("ruleset_hash:", rs.ruleset_hash)
print("rules:", len(rs.rules), "fixtures:", len(fixtures))
print("replay recall:", replay["recall"], f"({replay['correct']}/{replay['items']})")
print("mismatches:", len(replay["mismatches"]), "collisions:", len(collisions), "wrong:", len(wrong))
print("no_match:", len(no_match))
print("checks:", json.dumps(result["checks"], ensure_ascii=False))
print("hits==derived для всех правил:", len(overfit_exact) == len(candidate_rules))
print("name_diff_pids:", name_diff)
