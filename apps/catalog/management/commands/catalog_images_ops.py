"""Контур обратимости прогонов сбора изображений товаров (ИЗО-02).

`pg_dump` файлы в media-томе не покрывает, поэтому обратимость требует ДВУХ
снимков: дампа БД и снимка файловой системы. Эта команда даёт вторую половину
и весь цикл вокруг неё.

    # снимок «до» (read-only)
    catalog_images_ops --mode snapshot --out scratchpad/izo/snapshot-before.json

    # что даст прогон: добавится / отлетит дублем
    catalog_images_ops --mode plan --candidates scratchpad/izo/candidates.json

    # откат конкретного прогона (по умолчанию dry-run, ничего не удаляет)
    catalog_images_ops --mode rollback --source resanta --since 2026-08-08T00:00:00Z
    catalog_images_ops --mode rollback --source resanta --since ... --apply

    # сверка БД ↔ файлы после прогона или отката
    catalog_images_ops --mode audit

Гарантии:

- **dry-run по умолчанию.** Удаление происходит только при явном `--apply`.
- **`manual` неприкосновенен**: `--source manual` — отказ, а не предупреждение.
- **rollback с `--apply` удаляет и записи, и файлы прогона**: `apply_rollback`
  сносит файлы удаляемых записей (`path.unlink()`), считая `files_deleted`/
  `files_absent`. НЕ удаляются только осиротевшие файлы (не привязанные ни к
  одной записи) — они лишь показываются в snapshot/audit, чистка media отдельное
  решение владельца (на стенде их уже 37 при 107 записях).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.image_reversibility import (
    RollbackRefused,
    apply_rollback,
    audit,
    build_plan,
    build_rollback_plan,
    build_snapshot,
)
from apps.catalog.models import ImageSource

MODES = ("snapshot", "plan", "rollback", "audit")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CommandError(f"не разобрал дату {value!r}: нужен ISO-8601") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class Command(BaseCommand):
    help = "Снимок / план / откат / post-audit прогона сбора изображений товаров."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=MODES, required=True)
        parser.add_argument("--out", help="Файл для JSON-результата (иначе только сводка).")
        parser.add_argument(
            "--subdir",
            default="products",
            help="Поддерево media со снимками товаров (по умолчанию products).",
        )
        parser.add_argument("--candidates", help="mode=plan: JSON-список кандидатов прогона.")
        parser.add_argument(
            "--source",
            choices=[s for s in ImageSource.values],
            help="mode=rollback: источник прогона. manual запрещён.",
        )
        parser.add_argument("--since", help="mode=rollback: нижняя граница fetched_at (ISO).")
        parser.add_argument("--until", help="mode=rollback: верхняя граница fetched_at (ISO).")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Снять dry-run и действительно удалить записи и файлы прогона.",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        subdir = options["subdir"]
        handler = {
            "snapshot": self._snapshot,
            "plan": self._plan,
            "rollback": self._rollback,
            "audit": self._audit,
        }[mode]
        try:
            payload = handler(options, subdir)
        except RollbackRefused as exc:
            raise CommandError(str(exc)) from None
        self._write_out(options.get("out"), payload)

    # --- режимы ---------------------------------------------------------

    def _snapshot(self, options, subdir: str) -> dict:
        payload = build_snapshot(subdir)
        self.stdout.write("СНИМОК «ДО»")
        self.stdout.write(f"  записей ProductImage: {payload['records_total']}")
        for source, count in sorted(payload["records_by_source"].items()):
            self.stdout.write(f"    {source}: {count}")
        self.stdout.write(f"  файлов в media/{subdir}: {payload['files_total']}")
        self._report_orphans(payload["orphan_files_total"])
        self.stdout.write(
            "  ВНИМАНИЕ: снимок покрывает только файлы. Вторая половина обратимости — pg_dump."
        )
        return payload

    def _plan(self, options, subdir: str) -> dict:
        path = options.get("candidates")
        if not path:
            raise CommandError("mode=plan требует --candidates FILE")
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        candidates = raw["items"] if isinstance(raw, dict) else raw
        payload = build_plan(candidates)
        self.stdout.write("ПЛАН ПРОГОНА")
        self.stdout.write(f"  кандидатов:            {payload['candidates_total']}")
        self.stdout.write(f"  будет добавлено:       {payload['add']}")
        self.stdout.write(f"  дубль по URL:          {payload['skip_same_url']}")
        self.stdout.write(f"  дубль по checksum:     {payload['skip_same_checksum']}")
        self.stdout.write(f"  негодных кандидатов:   {payload['invalid']}")
        return payload

    def _rollback(self, options, subdir: str) -> dict:
        source = options.get("source")
        if not source:
            raise CommandError("mode=rollback требует --source")
        plan = build_rollback_plan(
            source=source,
            since=_parse_dt(options.get("since")),
            until=_parse_dt(options.get("until")),
            subdir=subdir,
        )
        self.stdout.write(f"ОТКАТ ПРОГОНА source={source}")
        self.stdout.write(f"  окно fetched_at:       {plan['since']} … {plan['until']}")
        self.stdout.write(f"  записей под удаление:  {plan['records_to_delete']}")
        self.stdout.write(f"  файлов под удаление:   {plan['files_to_delete']}")
        self.stdout.write(f"  записей без файла:     {plan['files_missing']}")
        self.stdout.write(f"  manual не тронут:      {plan['manual_untouched']} записей")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("  DRY-RUN: ничего не удалено. Применить: --apply")
            )
            plan["applied"] = False
            return plan

        result = apply_rollback(plan)
        plan["applied"] = True
        plan["result"] = result
        self.stdout.write(
            self.style.SUCCESS(
                f"  ПРИМЕНЕНО: записей {result['records_deleted']}, "
                f"файлов {result['files_deleted']} (не найдено {result['files_absent']})"
            )
        )
        after = audit(subdir)
        plan["post_audit"] = after
        self.stdout.write("  POST-AUDIT")
        self._audit_summary(after, indent="    ")
        return plan

    def _audit(self, options, subdir: str) -> dict:
        payload = audit(subdir)
        self.stdout.write("POST-AUDIT (БД против файлов)")
        self._audit_summary(payload, indent="  ")
        return payload

    # --- вывод ----------------------------------------------------------

    def _audit_summary(self, payload: dict, indent: str = "  ") -> None:
        self.stdout.write(f"{indent}записей ProductImage:  {payload['records_total']}")
        self.stdout.write(f"{indent}файлов в media:        {payload['files_total']}")
        self.stdout.write(f"{indent}запись без файла:      {payload['missing_file_total']}")
        self.stdout.write(f"{indent}checksum разошёлся:    {payload['checksum_mismatch_total']}")
        self.stdout.write(f"{indent}записей без checksum:  {payload['without_checksum_total']}")
        self._report_orphans(payload["orphan_files_total"], indent=indent)

    def _report_orphans(self, count: int, indent: str = "  ") -> None:
        line = f"{indent}осиротевших файлов:    {count}"
        if count:
            self.stdout.write(self.style.WARNING(line + "  (НЕ удаляются: решение владельца)"))
        else:
            self.stdout.write(line)

    def _write_out(self, out: str | None, payload: dict) -> None:
        if not out:
            return
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(f"JSON записан: {path}")
