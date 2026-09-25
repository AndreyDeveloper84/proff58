"""Phase 8 · ступень 1 — мутационная проверка guard'ов.

Для ключевых негативных сценариев доказываем, что сценарий ловит ИМЕННО
заявленный guard, а не побочный эффект: guard искусственно снимается
(monkeypatch/точечная мутация состояния в рантайме, БЕЗ правки исходников),
и сценарий обязан перестать падать.

Все прогоны — dry-run. Мутации состояния БД выполняются внутри
transaction.atomic() и откатываются. Отпечаток каталога сверяется снаружи.

Usage:
    PH8_RUN4=<uuid> manage.py shell -c "exec(open('scratchpad/phase8/run_mutations.py').read())"
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

import apps.catalog.management.commands.catalog_queue_import as imp_mod
from apps.catalog.models import CatalogProcessingItem, CatalogProcessingRun
from apps.catalog.queue_contract import _allowed_tool_type_options as real_options

TMP = Path("scratchpad/phase8/tmp-negatives").resolve()
RUN4 = os.environ["PH8_RUN4"]
RUN = CatalogProcessingRun.objects.get(pk=RUN4)


class _Rollback(Exception):
    pass


def do_import(path: Path) -> tuple[str, str]:
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            call_command("catalog_queue_import", file=str(path), allow_external_path=True)
    except CommandError as exc:
        return "CommandError", str(exc)
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__, str(exc)
    text = buf.getvalue()
    start, end = text.find("{"), text.find("}")
    stats = {}
    if start >= 0 < end:
        try:
            stats = json.loads(text[start : end + 1])
        except Exception:  # noqa: BLE001
            pass
    detail = json.dumps(
        {k: stats.get(k) for k in ("created", "would_create", "errors", "skipped")},
        ensure_ascii=False,
    )
    item_errors = [line.strip() for line in text.splitlines() if line.strip().startswith("- ")]
    if item_errors:
        detail += " || item-errors: " + "; ".join(dict.fromkeys(item_errors))
    return "OK(exit0)", detail


def report(case: str, guard: str, before: tuple, after: tuple) -> None:
    print(f"--- {case} · guard: {guard}")
    print(f"    guard ВКЛЮЧЁН: {before[0]} | {before[1][:160]}")
    print(f"    guard СНЯТ   : {after[0]} | {after[1][:160]}")
    verdict = "GUARD ДОКАЗАН" if before != after else "GUARD НЕ ДОКАЗАН"
    print(f"    ВЕРДИКТ: {verdict}\n")


# --- M1: JSON Schema --------------------------------------------------------
p = TMP / "n2-schema.result.json"
before = do_import(p)
with mock.patch.object(imp_mod, "_schema_validation"):
    after = do_import(p)
report("N2", "_schema_validation (JSON Schema draft-07)", before, after)

# --- M2: allowed_options (canonical manifest словарь) -----------------------
p = TMP / "n5-unknown-option.result.json"
before = do_import(p)
fake = {"slug": "ph8-syn-fake-tool-type", "value": "PH8-SYN FAKE"}
with (
    mock.patch.object(imp_mod, "_allowed_tool_type_options", lambda: [*real_options(), fake]),
    mock.patch.object(imp_mod, "_taxonomy_hash", lambda options: RUN.taxonomy_hash),
):
    after = do_import(p)
report("N5", "allowed_options — словарь tool_type", before, after)

# --- M3: domain validation (identity gate, файловый слой) -------------------
p = TMP / "n16-changes-without-identity.result.json"
before = do_import(p)
with mock.patch.object(imp_mod, "_domain_validation"):
    after = do_import(p)
report("N16", "_domain_validation (identity gate)", before, after)

# --- M4: export_checksum ----------------------------------------------------
p = TMP / "n13-export-checksum.result.json"
before = do_import(p)
try:
    with transaction.atomic():
        run = CatalogProcessingRun.objects.get(pk=RUN4)
        stats = dict(run.stats or {})
        stats["last_export_checksum"] = "f" * 64
        run.stats = stats
        run.save(update_fields=["stats"])
        after = do_import(p)
        raise _Rollback
except _Rollback:
    pass
report("N13", "сверка export_checksum с run.stats.last_export_checksum", before, after)

# --- M5: input_hash item ----------------------------------------------------
p = TMP / "n15-input-hash.result.json"
before = do_import(p)
try:
    with transaction.atomic():
        item = CatalogProcessingItem.objects.get(run_id=RUN4, product_ref=1)
        item.input_hash = "f" * 64
        item.save(update_fields=["input_hash"])
        after = do_import(p)
        raise _Rollback
except _Rollback:
    pass
report("N15", "сверка item.input_hash со снимком в result", before, after)

# --- M6: taxonomy_hash ------------------------------------------------------
p = TMP / "n14-taxonomy-hash.result.json"
before = do_import(p)
try:
    with transaction.atomic():
        run = CatalogProcessingRun.objects.get(pk=RUN4)
        run.taxonomy_hash = "f" * 64
        run.save(update_fields=["taxonomy_hash"])
        with mock.patch.object(imp_mod, "_taxonomy_hash", lambda options: "f" * 64):
            after = do_import(p)
        raise _Rollback
except _Rollback:
    pass
report("N14", "сверка taxonomy_hash result ↔ run ↔ живой словарь", before, after)

print("МУТАЦИИ ЗАВЕРШЕНЫ — все изменения БД откатаны")
print("контроль состояния run:", CatalogProcessingRun.objects.get(pk=RUN4).taxonomy_hash)
print(
    "контроль input_hash item1:",
    CatalogProcessingItem.objects.get(run_id=RUN4, product_ref=1).input_hash,
)
