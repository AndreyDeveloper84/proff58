"""Откат применённого ``tool_type`` по паре снимков (Wave 7.1 / Stage H5).

``--from`` — состояние, которое ожидается в БД сейчас (что записал forward-прогон);
``--to`` — состояние, к которому возвращаемся (снимок «до»). Решение по каждому
товару принимается сравнением с обоими снимками, поэтому повторный запуск —
no-op, а изменившийся baseline даёт **conflict**, а не молчаливую перезапись.

По умолчанию — dry-run: команда только печатает план. Запись требует явного
``--apply`` и идёт одной транзакцией; после записи автоматически выполняется
post-audit (пересборка снимка и сверка с целевым).

Exit codes: 0 — план исполним / откат применён и post-audit пройден;
1 — conflict (baseline изменился), ничего не записано; 2 — невалидные артефакты;
3 — internal / post-audit не сошёлся.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.tool_type_rollback import (
    EXIT_CONFLICT,
    EXIT_INTERNAL,
    EXIT_INVALID,
    RollbackError,
    apply_rollback,
    load_snapshot,
    plan_rollback,
    verify_post_state,
)


class Command(BaseCommand):
    help = "Откат tool_type по паре снимков (dry-run по умолчанию, запись — только --apply)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from", required=True, help="Снимок ожидаемого текущего состояния (после записи)."
        )
        parser.add_argument("--to", required=True, help="Снимок «до» — цель отката.")
        parser.add_argument(
            "--apply", action="store_true", help="Применить откат (иначе только план)."
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        try:
            from_doc = load_snapshot(options["from"], label="from")
            to_doc = load_snapshot(options["to"], label="to")
            plan = plan_rollback(from_doc, to_doc)
        except RollbackError as exc:
            raise CommandError(str(exc), returncode=EXIT_INVALID) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"internal rollback error: {exc}", returncode=EXIT_INTERNAL) from exc

        counts = plan.counts
        self.stdout.write(
            f"rows={len(plan.entries)} noop={counts['noop']} write={counts['write']} "
            f"conflict={counts['conflict']}"
        )
        for entry in plan.conflicts[:20]:
            self.stdout.write(
                f"  conflict product={entry['product_id']} reason={entry['reason']} "
                f"from={entry['from_option_slug']!r} to={entry['to_option_slug']!r} "
                f"live={entry['live_option_slug']!r}"
            )
        if not plan.feasible:
            raise CommandError(
                f"откат не выполнен: conflict по {counts['conflict']} товарам "
                "(baseline изменился — нужен новый снимок и переплан)",
                returncode=EXIT_CONFLICT,
            )

        if not options["apply"]:
            self.stdout.write("mode=dry-run (запись требует --apply)")
            return

        try:
            stats = apply_rollback(plan)
        except RollbackError as exc:
            raise CommandError(str(exc), returncode=EXIT_CONFLICT) from exc
        audit = verify_post_state(to_doc)
        self.stdout.write(f"mode=apply written={stats['written']} noop={stats['noop']}")
        for diff in audit["diffs"][:20]:
            self.stdout.write(f"  post-audit diff: {diff}")
        if not audit["passed"]:
            raise CommandError(
                f"post-audit не сошёлся: {len(audit['diffs'])} расхождений",
                returncode=EXIT_INTERNAL,
            )
        self.stdout.write(f"post-audit=PASS rows_checked={audit['rows_checked']}")
