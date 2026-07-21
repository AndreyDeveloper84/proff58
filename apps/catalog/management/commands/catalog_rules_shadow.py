"""Read-only shadow-прогон ruleset по пулу товаров (Phase 6.0).

НЕ требует FEATURES["catalog_processing"]: команда не пишет в каталог
вообще — единственный выходной артефакт JSON-отчёт. Rules как proposals
(этап 6.1) включаются отдельным решением после gate 6.0.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.processing import canonical_hash
from apps.catalog.queue_contract import _allowed_tool_type_options, _taxonomy_hash
from apps.catalog.rules_engine import (
    TIER_CANDIDATE,
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_ruleset,
    validate_against_taxonomy,
)

DEFAULT_OUT_DIR = Path(settings.BASE_DIR) / "var" / "catalog-processing" / "shadow"


def _pool_queryset(pool: str, *, has_tool_type: bool = False):
    """Критерии пула из плана Phase 6 (строже catalog_queue_create):
    is_active, content_locked=False, непустой article, без PAV tool_type
    с value_option; in-stock добавляет available_quantity > 0.
    ``has_tool_type=True`` переворачивает tool_type-фильтр: используется
    только для подсчёта исключённых (у них уже есть tool_type)."""
    has_tt = ProductAttributeValue.objects.filter(
        product_id=OuterRef("pk"),
        attribute__slug="tool_type",
        value_option__isnull=False,
    )
    qs = (
        Product.objects.annotate(_has_tt=Exists(has_tt))
        .filter(_has_tt=has_tool_type, is_active=True, content_locked=False)
        .exclude(article="")
        .order_by("pk")
    )
    if pool == "in-stock":
        qs = qs.filter(available_quantity__gt=0)
    return qs


def _sample_key(seed: int, product_id: int) -> str:
    return hashlib.sha256(f"{seed}:{product_id}".encode()).hexdigest()


class Command(BaseCommand):
    help = "Read-only shadow-прогон ruleset tool_type: coverage, коллизии, sample."

    def add_arguments(self, parser):
        parser.add_argument("--ruleset", type=str, default=None, help="Путь к ruleset JSON.")
        parser.add_argument(
            "--pool",
            type=str,
            default="in-stock",
            choices=["in-stock", "all"],
            help="Пул: in-stock (с остатком) или all (без stock-фильтра).",
        )
        parser.add_argument("--sample-size", type=int, default=0)
        parser.add_argument("--seed", type=int, default=20260721)
        parser.add_argument(
            "--replay-corpus",
            type=str,
            default=None,
            help="JSON applied-корпуса для regression replay (НЕ gate).",
        )
        parser.add_argument("--out", type=str, default=None, help="Путь к JSON-отчёту.")

    def handle(self, *args, **options):
        ruleset = load_ruleset(Path(options["ruleset"]) if options["ruleset"] else None)

        unknown = validate_against_taxonomy(
            ruleset,
            {o["slug"] for o in _allowed_tool_type_options()},
        )
        if unknown:
            raise CommandError(f"Slugs правил отсутствуют в allowed options: {unknown}")
        violations = check_negative_fixtures(ruleset)
        if violations:
            raise CommandError(f"Negative fixtures нарушены: {violations}")

        candidate_rules = [r for r in ruleset.rules if r.tier == TIER_CANDIDATE]
        regression_rules = [r for r in ruleset.rules if r.tier != TIER_CANDIDATE]

        predictions, collisions = [], []
        no_match = 0
        regression_hits = 0
        # Товары с существующим tool_type исключаются на уровне пула и не
        # оцениваются вовсе (решение 3: перезапись запрещена) — считаем их
        # зеркальным queryset; in-loop ветка ниже остаётся как защита.
        excluded = _pool_queryset(options["pool"], has_tool_type=True).count()
        pool_qs = _pool_queryset(options["pool"])
        pool_size = pool_qs.count()
        for product in pool_qs.iterator(chunk_size=500):
            facts = ProductFacts(
                product_id=product.pk,
                name=product.name or "",
                original_name=product.original_name or "",
                brand=product.brand or "",
                source_group=product.source_group or "",
                article=product.article or "",
                has_tool_type=getattr(product, "_has_tt", False),
            )
            verdict = evaluate_product(candidate_rules, facts)
            if verdict.status == "excluded_existing_tool_type":
                excluded += 1
            elif verdict.status == "collision":
                collisions.append(
                    {
                        "product_id": verdict.product_id,
                        "slugs": list(verdict.slugs),
                        "rule_refs": list(verdict.rule_refs),
                    }
                )
            elif verdict.status == "prediction":
                predictions.append(
                    {
                        "product_id": verdict.product_id,
                        "option_slug": verdict.option_slug,
                        "rule_refs": list(verdict.rule_refs),
                        "evidence": {
                            "name": facts.name,
                            "original_name": facts.original_name,
                            "brand": facts.brand,
                            "source_group": facts.source_group,
                            "article": facts.article,
                        },
                    }
                )
            else:
                no_match += 1
            if (
                regression_rules
                and evaluate_product(regression_rules, facts).status == "prediction"
            ):
                regression_hits += 1

        per_rule_hits: dict[str, int] = {}
        for p in predictions:
            for ref in p["rule_refs"]:
                per_rule_hits[ref] = per_rule_hits.get(ref, 0) + 1

        sample_ids: list[int] = []
        if options["sample_size"] > 0 and predictions:
            ordered = sorted(
                predictions, key=lambda p: _sample_key(options["seed"], p["product_id"])
            )
            sample_ids = [p["product_id"] for p in ordered[: options["sample_size"]]]

        report = {
            "generated_at": timezone.now().isoformat(),
            "ruleset_id": ruleset.ruleset_id,
            "ruleset_hash": ruleset.ruleset_hash,
            "taxonomy_hash": _taxonomy_hash(_allowed_tool_type_options()),
            "pool": {"name": options["pool"], "size": pool_size},
            "counts": {
                "predictions": len(predictions),
                "collisions": len(collisions),
                "no_match": no_match,
                "excluded_existing_tool_type": excluded,
                "regression_tier_hits": regression_hits,
            },
            "per_rule_hits": dict(sorted(per_rule_hits.items())),
            "collisions": collisions,
            "predictions": sorted(predictions, key=lambda p: p["product_id"]),
            "sample": {
                "seed": options["seed"],
                "size": len(sample_ids),
                "product_ids": sample_ids,
            },
        }

        if options["replay_corpus"]:
            report["replay"] = self._replay(ruleset, Path(options["replay_corpus"]))

        out = (
            Path(options["out"])
            if options["out"]
            else (
                DEFAULT_OUT_DIR / f"rules_shadow_{ruleset.ruleset_hash[:12]}_{options['pool']}.json"
            )
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        out.write_text(payload, encoding="utf-8")
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.stdout.write(
            self.style.SUCCESS(
                f"pool={options['pool']} size={pool_size} "
                f"predictions={len(predictions)} collisions={len(collisions)} "
                f"report={out} sha256={digest}"
            )
        )

    @staticmethod
    def _replay(ruleset, corpus_path: Path) -> dict:
        """Regression replay на applied-корпусе. НЕ gate: правила выведены из
        этих же товаров (training leakage), см. план Phase 6 §6.0."""
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        rules = [r for r in ruleset.rules if r.tier == TIER_CANDIDATE]
        correct, mismatches = 0, []
        for item in corpus["items"]:
            facts = ProductFacts(
                product_id=item["product_id"],
                name=item.get("name", ""),
                original_name=item.get("original_name", ""),
                brand=item.get("brand", ""),
                source_group=item.get("source_group", ""),
                article=item.get("article", ""),
            )
            verdict = evaluate_product(rules, facts)
            predicted = verdict.option_slug if verdict.status == "prediction" else ""
            if predicted == item["applied_option_slug"]:
                correct += 1
            else:
                mismatches.append(
                    {
                        "product_id": item["product_id"],
                        "expected": item["applied_option_slug"],
                        "predicted": predicted,
                        "status": verdict.status,
                    }
                )
        total = len(corpus["items"])
        recall = round(correct / total, 4) if total else 0.0
        return {
            "corpus_id": corpus.get("corpus_id", ""),
            "corpus_hash": canonical_hash(corpus),
            "items": total,
            "correct": correct,
            "recall": recall,
            "expected_recall": corpus.get("expected_recall"),
            "mismatches": mismatches,
        }
