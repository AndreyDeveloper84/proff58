"""Wave 7.1 / H4.6 — негативная матрица H2 на ПЕРЕВЫПУЩЕННОМ (canonical) sample.

Каждый сценарий обязан дать ненулевой exit code. Испорченные артефакты
создаются только во временном каталоге; data/ и fixtures/ не изменяются.

Запуск: uv run python -X utf8 scratchpad/wave7/h4_negative_matrix.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_SECRET_KEY", "h4-local")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402

from apps.catalog.processing import canonical_hash  # noqa: E402
from apps.catalog.rules_release import (  # noqa: E402
    RELEASE_MANIFEST_PATH,
    build_release_manifest,
    canonical_bytes,
    canonical_hash_of,
)

FIX = ROOT / "apps/catalog/tests/fixtures"
SAMPLE = FIX / "phase7d-gate-sample-official.json"
LABELS = FIX / "phase7d-labels.json"
RULESET = ROOT / "data/catalog_processing_rules/tool_type.v2.json"
RULESET_V1 = ROOT / "data/catalog_processing_rules/tool_type.v1.json"
LEGACY = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"

TMP = Path(tempfile.mkdtemp(prefix="h4-neg-"))
RESULTS: list[tuple[str, int, str, str]] = []


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _dump(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return Path(p)


def rebound(sample: dict, name: str):
    """Записать sample + перепривязанные labels во временный каталог."""
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    labels = _load(LABELS)
    labels["sample_hash"] = canonical_hash(sample)
    return _dump(d / "sample.json", sample), _dump(d / "labels.json", labels)


def run(scenario: str, command: str, expect: int, **kwargs) -> None:
    buf = StringIO()
    try:
        call_command(command, stdout=buf, stderr=buf, **kwargs)
        code, msg = 0, "(exit 0 — СЦЕНАРИЙ НЕ ЗАБЛОКИРОВАН)"
    except CommandError as exc:
        code = getattr(exc, "returncode", 1)
        msg = str(exc).splitlines()[0][:150]
    except Exception as exc:  # noqa: BLE001
        code, msg = -1, f"{type(exc).__name__}: {exc}"[:150]
    verdict = "OK" if code == expect else "!!! ОТКЛОНЕНИЕ"
    RESULTS.append((scenario, code, msg, verdict))
    print(f"[{verdict}] exit={code} (ожидалось {expect}) — {scenario}\n        {msg}")


GATE = "catalog_rules_gate_validate"
REL = "catalog_rules_release_manifest"

print("=== негативная матрица H4 (sample на canonical binding) ===\n")

# 1. legacy taxonomy binding без флага
s, lb = rebound({**_load(SAMPLE), "taxonomy_hash": LEGACY}, "legacy-bind")
run("sample с legacy taxonomy_hash, gate без флага", GATE, 2, gate_sample=str(s), labels=str(lb))
run("тот же sample → release --check", REL, 2, check=True, gate_sample=str(s), labels=str(lb))

# 2. полностью чужой taxonomy_hash (не legacy, не canonical)
s, lb = rebound({**_load(SAMPLE), "taxonomy_hash": "0" * 64}, "foreign-tax")
run("sample с чужим taxonomy_hash", GATE, 2, gate_sample=str(s), labels=str(lb))
run(
    "чужой taxonomy_hash + legacy-флаг на ДРУГОЙ хэш",
    GATE,
    2,
    gate_sample=str(s),
    labels=str(lb),
    allow_legacy_taxonomy_hash=LEGACY,
)

# 3. labels не перепривязаны (stale sample_hash) — ключевой для H4
d = TMP / "stale-labels"
d.mkdir(parents=True, exist_ok=True)
stale = _load(LABELS)
stale["sample_hash"] = "888980e7209c27026c13f56152330e5264d8da7103345fefb685713f8635a6db"
run(
    "labels.sample_hash от СТАРОГО (legacy) sample — не перепривязаны",
    GATE,
    2,
    gate_sample=str(SAMPLE),
    labels=str(_dump(d / "labels.json", stale)),
)

# 4. подделанные predictions
sample = _load(SAMPLE)
sample["rows"][0]["predicted_option_slug"] = "perforatory"
s, lb = rebound(sample, "forged-pred")
run("подделан predicted_option_slug", GATE, 2, gate_sample=str(s), labels=str(lb))

# 5. подделанный facts_hash
sample = _load(SAMPLE)
sample["rows"][0]["facts_hash"] = "f" * 64
s, lb = rebound(sample, "forged-facts")
run("подделан facts_hash", GATE, 2, gate_sample=str(s), labels=str(lb))

# 6. подделанные rule_refs
sample = _load(SAMPLE)
sample["rows"][0]["rule_refs"] = ["tt-ne-sushchestvuet"]
s, lb = rebound(sample, "forged-refs")
run("подделаны rule_refs", GATE, 2, gate_sample=str(s), labels=str(lb))

# 7. подделанный collision_count
sample = _load(SAMPLE)
sample["collision_count"] = 7
s, lb = rebound(sample, "forged-coll")
run("подделан collision_count", GATE, 2, gate_sample=str(s), labels=str(lb))

# 8. испорченный ruleset
data = _load(RULESET)
data["rules"][0]["match"].setdefault("name_keywords_any", []).append("tampered-h4")
tampered_rs = _dump(TMP / "tool_type.v2.tampered.json", data)
run(
    "испорченный ruleset (+keyword)",
    GATE,
    2,
    gate_sample=str(SAMPLE),
    labels=str(LABELS),
    ruleset=str(tampered_rs),
)
run("тот же ruleset → release --check", REL, 2, check=True, ruleset=str(tampered_rs))

# 9. чужой ruleset (исторический v1)
if RULESET_V1.exists():
    run(
        "чужой ruleset (исторический v1 вместо v2)",
        GATE,
        2,
        gate_sample=str(SAMPLE),
        labels=str(LABELS),
        ruleset=str(RULESET_V1),
    )
else:
    print("[SKIP] tool_type.v1.json отсутствует")

# 10. thresholds: sample обрезан до 99 строк
sample = _load(SAMPLE)
keep = {r["product_id"] for r in sample["rows"][:99]}
sample["rows"] = sample["rows"][:99]
d = TMP / "short"
d.mkdir(parents=True, exist_ok=True)
labels = _load(LABELS)
labels["labels"] = [x for x in labels["labels"] if x["product_id"] in keep]
labels["sample_hash"] = canonical_hash(sample)
run(
    "sample обрезан до 99 строк (thresholds)",
    GATE,
    1,
    gate_sample=str(_dump(d / "sample.json", sample)),
    labels=str(_dump(d / "labels.json", labels)),
)

# 11. release manifest: подделан без пересчёта canonical_hash
doc, _ = build_release_manifest()
bad = json.loads(json.dumps(doc))
bad["canonical"]["gate"]["metrics"]["precision"] = 1.0
p = TMP / "rel-tampered-hash.json"
p.write_bytes(canonical_bytes(bad))  # canonical_hash остался старым
run("release manifest: canonical_hash не пересчитан", REL, 2, check=True, manifest=str(p))

# 12. release manifest: самосогласован, но разошёлся с пересчётом
drift = json.loads(json.dumps(doc))
drift["canonical"]["inputs"]["ruleset"]["rules"] = 999
drift["canonical_hash"] = canonical_hash_of(drift["canonical"])
p = TMP / "rel-drift.json"
p.write_bytes(canonical_bytes(drift))
run("release manifest: drift (rules=999), hash пересчитан", REL, 2, check=True, manifest=str(p))

# 13. release manifest отсутствует / битый / без canonical
run("release manifest отсутствует", REL, 2, check=True, manifest=str(TMP / "no-such.json"))
p = TMP / "broken.json"
p.write_text("{not json", encoding="utf-8")
run("release manifest — битый JSON", REL, 2, check=True, manifest=str(p))
p = TMP / "nocanon.json"
p.write_text('{"foo": 1}', encoding="utf-8")
run("release manifest без секции canonical", REL, 2, check=True, manifest=str(p))

# 14. существующий отличающийся файл без --force
p = TMP / "existing.json"
p.write_text('{"canonical": {}, "canonical_hash": "x"}', encoding="utf-8")
before = p.read_bytes()
run("существующий отличающийся manifest без --force", REL, 2, manifest=str(p))
print(f"        файл не тронут: {p.read_bytes() == before}")

# --- контроль: штатные артефакты не изменены ---
print("\n=== контроль неизменности штатных артефактов ===")
import hashlib  # noqa: E402

for f in (SAMPLE, LABELS, RULESET, RELEASE_MANIFEST_PATH):
    print(f"  {f.name}: sha256={hashlib.sha256(f.read_bytes()).hexdigest()[:16]}…")

shutil.rmtree(TMP, ignore_errors=True)

bad_rows = [r for r in RESULTS if r[3] != "OK"]
print(f"\nИТОГО: {len(RESULTS)} сценариев, отклонений: {len(bad_rows)}")
raise SystemExit(1 if bad_rows else 0)
