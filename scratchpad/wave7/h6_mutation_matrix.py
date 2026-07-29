"""H6: двусторонняя проверка guard'ов повторной сверки baseline.

Для каждого guard'а дефект возвращается в исходник, привязанные тесты обязаны
упасть, файл восстанавливается в finally. Рецептура — как в h5_mutation_matrix.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "apps" / "catalog" / "tool_type_rollback.py"
TESTS = "apps/catalog/tests/test_h5_negative_matrix.py"

MUTATIONS = [
    (
        "recheck_removed — повторная сверка baseline снята",
        '            decision, reason = _decide(\n'
        '                live_now.get(entry["product_id"]),\n'
        '                entry["from_option_slug"],\n'
        '                entry["to_option_slug"],\n'
        '            )\n',
        '            decision, reason = ("write", "baseline_matches_from")\n',
        "test_baseline_changed_between_plan_and_apply_aborts_whole_write or "
        "test_pav_removed_between_plan_and_apply_aborts_write or "
        "test_concurrent_rollback_to_same_target_is_counted_as_noop",
    ),
    (
        "product_lock_removed — снята блокировка Product",
        '        list(Product.objects.select_for_update().filter(id__in=write_ids).order_by("id"))\n',
        '        list(Product.objects.filter(id__in=write_ids).order_by("id"))\n',
        "test_apply_locks_product_and_pav_rows",
    ),
    (
        "pav_lock_removed — снята блокировка ProductAttributeValue",
        "            ProductAttributeValue.objects.select_for_update()\n",
        "            ProductAttributeValue.objects.all()\n",
        "test_apply_locks_product_and_pav_rows",
    ),
    (
        "drift_not_fatal — дрейф baseline перестаёт быть отказом",
        "        if drifted:\n",
        "        if False and drifted:\n",
        "test_baseline_changed_between_plan_and_apply_aborts_whole_write or "
        "test_pav_removed_between_plan_and_apply_aborts_write",
    ),
]


def run(selector: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-k", selector, "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    original = SRC.read_text(encoding="utf-8")
    failures = 0
    try:
        for name, old, new, selector in MUTATIONS:
            if old not in original:
                print(f"SKIP  {name}: якорь не найден в исходнике")
                failures += 1
                continue
            SRC.write_text(original.replace(old, new, 1), encoding="utf-8")
            code = run(selector)
            ok = code != 0
            print(f"{'OK  ' if ok else 'FAIL'}  {name}: pytest exit={code} (ожидалось != 0)")
            if not ok:
                failures += 1
            SRC.write_text(original, encoding="utf-8")
    finally:
        SRC.write_text(original, encoding="utf-8")

    clean = run("between_plan_and_apply or concurrent_rollback or apply_locks")
    print(f"{'OK  ' if clean == 0 else 'FAIL'}  чистый прогон после восстановления: exit={clean}")
    if clean != 0:
        failures += 1
    print(f"\nитог: мутаций {len(MUTATIONS)}, провалов {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
