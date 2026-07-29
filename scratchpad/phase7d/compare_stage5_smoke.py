"""Stage C post-deploy smoke comparator (temporary tool, Phase 7D Stage 5).

Сравнивает staging smoke report (default ruleset, без --ruleset) с frozen
reference 7D official report по инвариантам F-5.4. Только чтение файлов.

Usage:
    python compare_stage5_smoke.py <smoke_report.json> [reference.json]
"""
import json
import sys

REFERENCE = "scratchpad/phase7d/phase7d-shadow-report-v2-official.json"

PIN_RULESET_ID = "tool_type.v2"
PIN_RULESET_HASH = "9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330"
PIN_TAXONOMY = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"
PIN_UNIVERSE = "82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8"

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def main():
    smoke_path = sys.argv[1]
    ref_path = sys.argv[2] if len(sys.argv) > 2 else REFERENCE
    s = json.load(open(smoke_path, encoding="utf-8"))
    r = json.load(open(ref_path, encoding="utf-8"))

    # 1. pinned hashes / ids
    check("ruleset_id == tool_type.v2", s.get("ruleset_id") == PIN_RULESET_ID, str(s.get("ruleset_id")))
    check("ruleset_hash == pin", s.get("ruleset_hash") == PIN_RULESET_HASH, str(s.get("ruleset_hash")))
    check("taxonomy_hash == pin", s.get("taxonomy_hash") == PIN_TAXONOMY, str(s.get("taxonomy_hash")))
    check("input_universe_hash == pin", s.get("input_universe_hash") == PIN_UNIVERSE, str(s.get("input_universe_hash")))

    # 2. counts / pool invariants
    c = s.get("counts", {})
    p = s.get("pool", {})
    check("predictions == 325", c.get("predictions") == 325, str(c.get("predictions")))
    check("counts.collisions == 0", c.get("collisions") == 0, str(c.get("collisions")))
    check("top-level collisions == []", s.get("collisions") == [], str(s.get("collisions"))[:100])
    check("rewrite_attempts == 0", p.get("rewrite_attempts") == 0, str(p.get("rewrite_attempts")))
    check("pool.size == 1593", p.get("size") == 1593, str(p.get("size")))
    check("pool.excluded_existing_tool_type == 18123", p.get("excluded_existing_tool_type") == 18123, str(p.get("excluded_existing_tool_type")))
    check("pool.typed_eligible_universe == 18123", p.get("typed_eligible_universe") == 18123, str(p.get("typed_eligible_universe")))
    check("matcher_version == 1.0", s.get("matcher_version") == "1.0", str(s.get("matcher_version")))

    # 3. ordered predictions == reference
    sp = [(x["product_id"], x["option_slug"], tuple(x["rule_refs"])) for x in s["predictions"]]
    rp = [(x["product_id"], x["option_slug"], tuple(x["rule_refs"])) for x in r["predictions"]]
    check("ordered predictions identical (n=325)", sp == rp, f"smoke n={len(sp)}, ref n={len(rp)}")

    # 4. per-rule counters == reference (4 counters × все правила)
    skeys, rkeys = set(s["per_rule"]), set(r["per_rule"])
    check("per_rule rule set identical", skeys == rkeys, f"smoke={len(skeys)}, ref={len(rkeys)}")
    bad = []
    for ref_name in sorted(skeys & rkeys):
        for ctr in ("raw_hits", "prediction_hits", "collision_hits", "same_slug_multi_hits"):
            if s["per_rule"][ref_name][ctr] != r["per_rule"][ref_name][ctr]:
                bad.append(f"{ref_name}.{ctr}: smoke={s['per_rule'][ref_name][ctr]} ref={r['per_rule'][ref_name][ctr]}")
    check("per_rule counters identical (4 x rules)", not bad, "; ".join(bad[:5]))

    # 5. monitoring case 31104 unchanged
    s31 = [x for x in s["predictions"] if x["product_id"] == 31104]
    r31 = [x for x in r["predictions"] if x["product_id"] == 31104]
    ok = (
        len(s31) == 1
        and s31[0]["option_slug"] == "svar-reduktory"
        and s31[0]["rule_refs"] == ["tt-svar-reduktory-regulyator"]
        and s31[0]["evidence"]["facts_hash"] == r31[0]["evidence"]["facts_hash"]
    )
    check(
        "31104 unchanged (svar-reduktory, same facts_hash)",
        ok,
        f"slug={s31[0]['option_slug'] if s31 else None}, refs={s31[0]['rule_refs'] if s31 else None}",
    )

    print()
    if failures:
        print(f"OVERALL: FAIL ({len(failures)} checks) — F-5.4 → rollback protocol")
        sys.exit(1)
    print("OVERALL: PASS — все инварианты F-5.4 совпали с frozen reference")


if __name__ == "__main__":
    main()
