"""Read-only reconciliation live tool_type taxonomy против canonical manifest (Wave 7.1/H1).

Показывает drift между БД и ``tool_type_taxonomy.v1.json`` без каких-либо записей.
Категории:

- blocking (``--fail-on blocking``, default): ``missing_in_live``,
  ``unexpected_in_live``, ``slug_value_mismatch``, ``used_outside_manifest``,
  ``ruleset_unknown_slug``;
- advisory (только отчёт / ``--fail-on any``): ``semantic_duplicate``,
  ``manifest_unused_option``, ``display_metadata_mismatch``,
  ``pending_business_review``.

Целевой инвариант: ``live operational taxonomy == canonical manifest``
(blocking drift = 0); advisory findings фиксируются, но не роняют проверку
по умолчанию. Любые изменения taxonomy — только через seed/отдельную
авторизацию, эта команда ничего не меняет.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.catalog.models import Attribute, ProductAttributeValue
from apps.catalog.rules_engine import load_ruleset, validate_against_taxonomy
from apps.catalog.taxonomy_manifest import load_manifest, taxonomy_identity_hash

TOOL_TYPE_SLUG = "tool_type"

BLOCKING = (
    "missing_in_live",
    "unexpected_in_live",
    "slug_value_mismatch",
    "used_outside_manifest",
    "ruleset_unknown_slug",
)
ADVISORY = (
    "semantic_duplicate",
    "manifest_unused_option",
    "display_metadata_mismatch",
    "pending_business_review",
)


class Command(BaseCommand):
    help = "Read-only reconciliation live tool_type taxonomy против canonical manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest",
            default=None,
            help="Путь к taxonomy manifest (default: canonical tool_type_taxonomy.v1.json)",
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument(
            "--fail-on",
            choices=["blocking", "any"],
            default="blocking",
            help="blocking (default): выход с ошибкой только при blocking drift; any: и advisory.",
        )
        parser.add_argument(
            "--ruleset",
            default=None,
            help="Путь к ruleset для ruleset_unknown_slug (default: default RULESET_PATH).",
        )

    def handle(self, *args, **options):
        try:
            manifest = load_manifest(options["manifest"])
        except (ValueError, FileNotFoundError) as exc:
            raise CommandError(str(exc)) from exc

        report = self._build_report(manifest, options["ruleset"])
        self._emit(report, options["format"])

        fail_on = options["fail_on"]
        blocking_bad = any(report["blocking"][k] for k in BLOCKING)
        advisory_bad = any(report["advisory"][k] for k in ADVISORY)
        if blocking_bad or (fail_on == "any" and advisory_bad):
            scope = "blocking drift" if blocking_bad else "advisory findings (fail-on=any)"
            raise CommandError(f"taxonomy reconciliation: {scope} — см. отчёт выше")

    # --- построение отчёта (только SELECT) ---

    def _build_report(self, manifest, ruleset_path, live=None) -> dict:
        if live is None:
            attribute = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
            live = list(attribute.options.all()) if attribute is not None else []
        usage = {
            row["value_option_id"]: row["n"]
            for row in ProductAttributeValue.objects.filter(
                value_option__attribute__slug=TOOL_TYPE_SLUG
            )
            .values("value_option_id")
            .annotate(n=Count("id"))
        }

        manifest_by_slug = {o.slug: o for o in manifest.options}
        live_by_slug = {o.slug: o for o in live}
        common = set(manifest_by_slug) & set(live_by_slug)

        missing_in_live = sorted(set(manifest_by_slug) - set(live_by_slug))
        unexpected_in_live = sorted(set(live_by_slug) - set(manifest_by_slug))
        slug_value_mismatch = sorted(
            s for s in common if live_by_slug[s].value != manifest_by_slug[s].value
        )
        used_outside_manifest = sorted(
            (slug, usage.get(live_by_slug[slug].id, 0))
            for slug in unexpected_in_live
            if usage.get(live_by_slug[slug].id, 0) > 0
        )
        by_value: dict[str, list[str]] = {}
        for o in live:
            by_value.setdefault(o.value, []).append(o.slug)
        semantic_duplicate = {v: sorted(s) for v, s in by_value.items() if len(s) > 1}
        manifest_unused_option = sorted(
            slug for slug in common if usage.get(live_by_slug[slug].id, 0) == 0
        )
        display_metadata_mismatch = sorted(
            s for s in common if live_by_slug[s].sort_order != manifest_by_slug[s].sort_order
        )
        pending_business_review = sorted(
            o.slug for o in manifest.options if o.review_status == "pending_business_review"
        )

        ruleset = load_ruleset(ruleset_path if ruleset_path else None)
        ruleset_unknown_slug = validate_against_taxonomy(ruleset, manifest.slugs)

        live_identity = taxonomy_identity_hash([{"slug": o.slug, "value": o.value} for o in live])
        return {
            "manifest": {
                "path": str(manifest.path),
                "manifest_version": manifest.manifest_version,
                "options": len(manifest.options),
                "taxonomy_identity_hash": manifest.identity_hash,
                "manifest_semantic_hash": manifest.semantic_hash,
            },
            "live": {
                "options": len(live),
                "taxonomy_identity_hash": live_identity,
            },
            "identity_equal": live_identity == manifest.identity_hash,
            "blocking": {
                "missing_in_live": missing_in_live,
                "unexpected_in_live": unexpected_in_live,
                "slug_value_mismatch": slug_value_mismatch,
                "used_outside_manifest": [
                    {"slug": slug, "pav_count": n} for slug, n in used_outside_manifest
                ],
                "ruleset_unknown_slug": ruleset_unknown_slug,
            },
            "advisory": {
                "semantic_duplicate": semantic_duplicate,
                "manifest_unused_option": manifest_unused_option,
                "display_metadata_mismatch": display_metadata_mismatch,
                "pending_business_review": pending_business_review,
            },
        }

    def _emit(self, report: dict, fmt: str) -> None:
        if fmt == "json":
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return
        m = report["manifest"]
        self.stdout.write(
            f"manifest v{m['manifest_version']} ({m['options']} options, "
            f"identity {m['taxonomy_identity_hash'][:12]}…) vs live "
            f"({report['live']['options']} options): identity_equal={report['identity_equal']}"
        )
        for group in ("blocking", "advisory"):
            for key, values in report[group].items():
                marker = "OK" if not values else ("!!" if group == "blocking" else "~~")
                self.stdout.write(f"  [{marker}] {group}/{key}: {len(values)}")
                for item in (
                    list(values)[:10] if not isinstance(values, dict) else list(values.items())[:10]
                ):
                    self.stdout.write(f"      - {item}")
