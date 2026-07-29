"""Wave 7.1 / H1: классификация 328 tool_type options (analysis artifact, не repo code).

Источники:
- staging dump: scratchpad/wave7/staging-tool_type-usage.json (id, slug, value, sort_order, pav_count)
- seed: data/tool_type_rules.json (extraction rules; value -> [(slug, category)])
- rulesets: data/catalog_processing_rules/tool_type.v2.json (default), tool_type.v1.json
Output: scratchpad/wave7/taxonomy-inventory.tsv + summary в stdout.
"""
import json
from collections import Counter, defaultdict

ROOT = "C:/Users/user/PycharmProjects/proff58"

staging = json.load(open(f"{ROOT}/scratchpad/wave7/staging-tool_type-usage.json", encoding="utf-8"))
seed_doc = json.load(open(f"{ROOT}/data/tool_type_rules.json", encoding="utf-8"))
v2 = json.load(open(f"{ROOT}/data/catalog_processing_rules/tool_type.v2.json", encoding="utf-8"))
v1 = json.load(open(f"{ROOT}/data/catalog_processing_rules/tool_type.v1.json", encoding="utf-8"))

# --- seed: value -> [(slug, category)] в порядке файла (load_tool_types: last wins) ---
seed_by_value = defaultdict(list)
for cat in seed_doc["categories"]:
    for r in cat.get("rules", []):
        if r.get("action") == "recategorize":
            continue
        seed_by_value[r["tool_type"]].append((r["slug"], cat["category"]))

seed_collisions = {v: sl for v, sl in seed_by_value.items() if len({s for s, _ in sl}) > 1}

# --- ruleset usage: slug -> rule_refs ---
def ruleset_usage(rs):
    out = defaultdict(list)
    for rule in rs["rules"]:
        out[rule["option_slug"]].append(rule["rule_ref"])
    return out

v2_use = ruleset_usage(v2)
v1_use = ruleset_usage(v1)

MANUAL_SRC = {
    428: "manual staging round 3",
    431: "manual staging round 4",
    432: "manual staging round 4",
    433: "manual staging round 5",
}

rows = []
for o in staging:
    slug, value, oid, pav = o["slug"], o["value"], o["id"], o["pav_count"]
    seed_entries = seed_by_value.get(value, [])
    seed_slugs = [s for s, _ in seed_entries]
    if slug in seed_slugs:
        seed_status = "in_seed"
        source = "seed"
    elif seed_entries:
        seed_status = f"seed_value_other_slug({';'.join(seed_slugs)})"
        source = "seed(other slug)"
    else:
        seed_status = "not_in_seed"
        source = MANUAL_SRC.get(oid, "unknown/legacy")
    coll = ""
    if value in seed_collisions:
        idx = sorted(seed_collisions).index(value) + 1
        coll = f"G{idx}"
    v2refs = ",".join(v2_use.get(slug, []))
    v1refs = "y" if slug in v1_use else ""
    if oid in MANUAL_SRC and v2refs:
        action, why = "include", "v2-required; back-port to manifest"
    elif pav == 0 and not v2refs:
        action, why = "include+review", "unused by products and ruleset"
    elif coll:
        action, why = "include+review", f"seed collision {coll}: staging slug vs seed winner"
    elif seed_status.startswith("seed_value_other_slug"):
        action, why = "include+review", "staging slug != current seed slug for same value"
    else:
        action, why = "include", ""
    rows.append(
        {
            "slug": slug, "value": value, "id": oid, "sort_order": o["sort_order"],
            "source": source, "used_by_v2": v2refs, "used_by_v1": v1refs,
            "pav_count": pav, "seed_status": seed_status, "collision_group": coll,
            "proposed_action": action, "rationale": why,
        }
    )

with open(f"{ROOT}/scratchpad/wave7/taxonomy-inventory.tsv", "w", encoding="utf-8") as f:
    f.write("slug\tvalue\tid\tsort_order\tsource\tused_by_v2\tused_by_v1\tpav_count\tseed_status\tcollision_group\tproposed_action\trationale\n")
    for r in rows:
        f.write("\t".join(str(r[k]) for k in ("slug", "value", "id", "sort_order", "source", "used_by_v2", "used_by_v1", "pav_count", "seed_status", "collision_group", "proposed_action", "rationale")) + "\n")

# --- summary ---
print("=== SUMMARY ===")
print("total:", len(rows))
print("seed_status counts:", Counter(r["seed_status"].split("(")[0] for r in rows))
print("proposed_action counts:", Counter(r["proposed_action"] for r in rows))
print("used_by_v2:", sum(1 for r in rows if r["used_by_v2"]), "| used_by_v1:", sum(1 for r in rows if r["used_by_v1"]))
print("pav_count==0:", [r["slug"] for r in rows if r["pav_count"] == 0])
print()
print("=== NOT IN SEED (15?) ===")
for r in rows:
    if r["seed_status"] == "not_in_seed":
        print(f'  id={r["id"]:>4} {r["slug"]:<28} {r["value"][:40]:<42} pav={r["pav_count"]:<5} v2={r["used_by_v2"] or "-":<30} src={r["source"]}')
print()
print("=== SEED VALUE COLLISIONS (value -> slugs in seed; staging slug) ===")
for v, sl in sorted(seed_collisions.items()):
    st = [r for r in rows if r["value"] == v]
    st_slug = st[0]["slug"] if st else "ABSENT-ON-STAGING"
    winner = sl[-1][0]
    flag = "OK" if st_slug == winner else "STAGING!=CURRENT-WINNER"
    print(f'  {v[:44]:<46} seed={[s for s,_ in sl]} staging={st_slug} last-wins={winner} [{flag}]')
print()
print("=== seed_value_other_slug rows ===")
for r in rows:
    if r["seed_status"].startswith("seed_value_other_slug"):
        print(f'  {r["slug"]:<28} {r["value"][:40]:<42} seed has: {r["seed_status"]}')
print()
print("=== v2 slugs not in seed ===")
for r in rows:
    if r["used_by_v2"] and r["seed_status"] == "not_in_seed":
        print(f'  {r["slug"]:<28} refs={r["used_by_v2"]}')
print("unused with usage>0 check: pav==0 rows:", [(r["slug"], r["used_by_v2"]) for r in rows if r["pav_count"] == 0])
