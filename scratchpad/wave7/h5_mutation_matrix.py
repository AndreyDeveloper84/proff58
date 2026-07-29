"""Двусторонняя проверка guard'ов H5: тест обязан падать при возврате дефекта.

Для каждого guard'а: искусственно портим исходник (возвращаем дефект) → гоняем
привязанный тест → он ОБЯЗАН упасть → восстанавливаем файл. В конце — один
чистый прогон всех задействованных тестов, который обязан быть зелёным.

Запуск: uv run python scratchpad/wave7/h5_mutation_matrix.py
Исходники всегда восстанавливаются (finally), даже при падении скрипта.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLLBACK = ROOT / "apps" / "catalog" / "tool_type_rollback.py"
REVERSE = ROOT / "apps" / "catalog" / "taxonomy_reverse.py"
T_ROLLBACK = "apps/catalog/tests/test_tool_type_rollback.py"
T_REVERSE = "apps/catalog/tests/test_taxonomy_reverse.py"
T_CLI = "apps/catalog/tests/test_tool_type_rollback_commands.py"

MUTATIONS = [
    (
        "G1 conflict-детекция: чужой baseline трактуется как штатная запись",
        ROLLBACK,
        '            entry.update(decision=DECISION_CONFLICT, reason="baseline_changed")',
        '            entry.update(decision=DECISION_WRITE, reason="baseline_changed")',
        [
            f"{T_ROLLBACK}::test_plan_reports_conflict_when_live_drifted_from_both_snapshots",
            f"{T_CLI}::test_rollback_conflict_exits_1_and_writes_nothing",
        ],
    ),
    (
        "G2 apply отказывается применять конфликтный план",
        ROLLBACK,
        "    counts = plan.counts\n    if not plan.feasible:",
        "    counts = plan.counts\n    if False:",
        [f"{T_ROLLBACK}::test_apply_refuses_plan_with_conflicts"],
    ),
    (
        "G3 атомарность записи (одна транзакция)",
        ROLLBACK,
        "    with transaction.atomic():\n        attribute = Attribute.objects.filter",
        "    if True:\n        attribute = Attribute.objects.filter",
        [f"{T_ROLLBACK}::test_partial_failure_leaves_no_half_applied_state"],
    ),
    (
        "G4 снимки обязаны покрывать одно множество товаров",
        ROLLBACK,
        "    if set(from_rows) != set(to_rows):",
        "    if False:",
        [f"{T_ROLLBACK}::test_plan_rejects_snapshots_covering_different_products"],
    ),
    (
        "G5 дрейф taxonomy_identity между снимком и live",
        ROLLBACK,
        "        if recorded != live_identity:",
        "        if False:",
        [f"{T_ROLLBACK}::test_plan_rejects_taxonomy_drift_between_snapshot_and_live"],
    ),
    (
        "G6 целевая опция обязана существовать в live-словаре",
        ROLLBACK,
        "    unknown = sorted(targets - live_slugs)",
        "    unknown = []",
        [f"{T_ROLLBACK}::test_plan_rejects_target_option_absent_in_live_taxonomy"],
    ),
    (
        "G7 самосогласованность canonical_hash снимка",
        ROLLBACK,
        '    if doc.get("canonical_hash") != actual:',
        "    if False:",
        [f"{T_ROLLBACK}::test_load_snapshot_rejects_tampered_canonical_hash"],
    ),
    (
        "G8 смежность версий манифеста N -> N-1",
        REVERSE,
        "    if dst.manifest_version != src.manifest_version - 1:",
        "    if False:",
        [
            f"{T_REVERSE}::test_plan_rejects_non_adjacent_manifest_version",
            f"{T_REVERSE}::test_plan_rejects_forward_direction",
        ],
    ),
    (
        "G9 исчезающая опция с товарами блокирует понижение",
        REVERSE,
        "            if pav_count == 0:",
        "            if True:",
        [f"{T_REVERSE}::test_disappearing_option_with_products_blocks_without_remap"],
    ),
    (
        "G10 remap только для реально исчезающих slug",
        REVERSE,
        '    stray = sorted(set(remap) - set(diff["disappearing"]))',
        "    stray = []",
        [f"{T_REVERSE}::test_remap_for_surviving_slug_is_rejected"],
    ),
    (
        "G11 удаление опций fail-closed по usage",
        REVERSE,
        "        if still_used:",
        "        if False:",
        [f"{T_REVERSE}::test_drop_refuses_when_option_still_carries_products"],
    ),
    (
        "G12 удаление опций запрещено на неисполнимом плане",
        REVERSE,
        '    if not plan.feasible:\n        raise ReverseMigrationError(\n            "план не feasible — удаление опций запрещено: "',
        '    if False:\n        raise ReverseMigrationError(\n            "план не feasible — удаление опций запрещено: "',
        [f"{T_REVERSE}::test_drop_refuses_infeasible_plan"],
    ),
]


def run_pytest(nodes: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *nodes],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode


def main() -> int:
    results = []
    for name, path, old, new, nodes in MUTATIONS:
        source = path.read_text(encoding="utf-8")
        if source.count(old) != 1:
            results.append((name, "SETUP-FAIL", f"якорь встречается {source.count(old)} раз"))
            continue
        try:
            path.write_text(source.replace(old, new), encoding="utf-8")
            code = run_pytest(nodes)
        finally:
            path.write_text(source, encoding="utf-8")
        verdict = "OK (тест упал на дефекте)" if code != 0 else "ПРОВАЛ (тест зелёный на дефекте)"
        results.append((name, "OK" if code != 0 else "FAIL", verdict))

    clean = run_pytest([T_ROLLBACK, T_REVERSE, T_CLI])
    print("=" * 78)
    for name, status, detail in results:
        print(f"[{status:^4}] {name}\n        {detail}")
    print("=" * 78)
    print(f"чистый прогон после восстановления: {'PASS' if clean == 0 else 'FAIL'}")
    bad = [r for r in results if r[1] != "OK"]
    print(f"итог: {len(results) - len(bad)}/{len(results)} guard'ов подтверждены обеими сторонами")
    return 1 if bad or clean != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
