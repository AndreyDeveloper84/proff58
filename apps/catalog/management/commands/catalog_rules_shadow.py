"""Read-only shadow-прогон ruleset по пулу товаров (Phase 6.0).

НЕ требует FEATURES["catalog_processing"]: команда не пишет в каталог
вообще — выходные артефакты только JSON-отчёт (v1.0) и опциональный
gate_sample (v1). Rules как proposals (этап 6.1) включаются отдельным
решением после gate 6.0.

Усиление по ревью 2026-07-21: snapshot-чтение REPEATABLE READ READ ONLY
(P1.6), версионирование отчёта и code_sha (P1.4), атомарная запись с
защитой от перезаписи (P1.5), per-rule метрики (P1.8), gate-артефакты
(P0.3), строгий pool-контракт с Trim(article) (P1.7).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Exists, OuterRef
from django.db.models.functions import Trim
from django.utils import timezone

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.processing import canonical_hash
from apps.catalog.queue_contract import _allowed_tool_type_options, _taxonomy_hash
from apps.catalog.rules_engine import (
    MATCHER_VERSION,
    TIER_CANDIDATE,
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_corpus,
    load_ruleset,
    validate_against_taxonomy,
    validate_gate_sample,
)

DEFAULT_OUT_DIR = Path(settings.BASE_DIR) / "var" / "catalog-processing" / "shadow"

REPORT_SCHEMA_VERSION = "1.0"
POOL_FILTER_VERSION = "1.0"
SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
FACT_KEYS = ("name", "original_name", "brand", "source_group", "article")
# volatile-поля исключаются из content_hash (P1.5)
VOLATILE_REPORT_KEYS = ("generated_at", "started_at", "finished_at", "duration_seconds")


def _eligible_qs(*, has_tool_type: bool):
    """Базовые критерии eligible (P1.7): активный, не content_locked,
    непустой (после Trim) article, наличие/отсутствие PAV tool_type
    с value_option."""
    has_tt = ProductAttributeValue.objects.filter(
        product_id=OuterRef("pk"), attribute__slug="tool_type", value_option__isnull=False
    )
    return (
        Product.objects.annotate(_has_tt=Exists(has_tt), _art=Trim("article"))
        .filter(_has_tt=has_tool_type, is_active=True, content_locked=False)
        .exclude(_art="")
    )


def _pool_queryset(pool: str, *, has_tool_type: bool = False):
    """in-stock добавляет available_quantity > 0. ``has_tool_type=True`` —
    зеркальный queryset исключённых (у них уже есть tool_type): они
    не оцениваются вовсе (решение 3: перезапись запрещена)."""
    qs = _eligible_qs(has_tool_type=has_tool_type)
    if pool == "in-stock":
        qs = qs.filter(available_quantity__gt=0)
    return qs.order_by("pk")


def _sample_key(seed: int, product_id: int) -> str:
    return hashlib.sha256(f"{seed}:{product_id}".encode()).hexdigest()


def _code_sha() -> str:
    """git rev-parse HEAD; fallback "unknown", когда git недоступен."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=settings.BASE_DIR,
        )
    except Exception:
        return "unknown"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else "unknown"


def _default_out_path(pool: str, ruleset_hash: str, started) -> Path:
    """Уникальное имя по UTC-таймстампу; при коллизии — суффикс -2, -3…"""
    stamp = started.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = DEFAULT_OUT_DIR / f"rules_shadow_{pool}_{stamp}_{ruleset_hash[:12]}.json"
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = base.with_name(f"{base.stem}-{i}{base.suffix}")
        if not candidate.exists():
            return candidate
    raise CommandError("Не удалось подобрать уникальное имя файла отчёта")


def _write_atomic(path: Path, payload: str) -> str:
    """tmp-файл в той же директории + os.replace; 0o600 на POSIX (P1.5).
    Запись бинарная: байты файла совпадают с payload на любой платформе
    (без трансляции \\n → \\r\\n на Windows), поэтому возвращаемый sha256 —
    всегда хэш фактических байтов файла."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    data = payload.encode("utf-8")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    if os.name == "posix":
        os.chmod(path, 0o600)
    return hashlib.sha256(data).hexdigest()


def _tally(per_rule: dict, verdict) -> None:
    """Per-rule счётчики по вердикту (P1.8): raw = правило сматчилось,
    prediction/collision — правило вошло в соответствующий вердикт,
    same_slug_multi — prediction сразу по нескольким правилам одного slug."""
    for ref in verdict.rule_refs:
        per_rule[ref]["raw_hits"] += 1
        if verdict.status == "prediction":
            per_rule[ref]["prediction_hits"] += 1
            if len(verdict.rule_refs) > 1:
                per_rule[ref]["same_slug_multi_hits"] += 1
        elif verdict.status == "collision":
            per_rule[ref]["collision_hits"] += 1


class Command(BaseCommand):
    help = "Read-only shadow-прогон ruleset tool_type: coverage, коллизии, sample, gate-артефакты."

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
        parser.add_argument(
            "--force",
            action="store_true",
            help="Разрешить перезапись существующих --out/--gate-sample-out.",
        )
        parser.add_argument(
            "--gate-sample-out",
            type=str,
            default=None,
            help="Путь к gate_sample артефакту (v1) для ручной разметки.",
        )
        parser.add_argument(
            "--corpus",
            type=str,
            default=None,
            help="JSON applied-корпуса: overlap-проверка gate_sample (training leakage).",
        )

    def handle(self, *args, **options):
        started = timezone.now()
        ruleset = load_ruleset(Path(options["ruleset"]) if options["ruleset"] else None)

        # --- snapshot-чтение (P1.6): ВСЕ запросы в одной транзакции ---
        # SET TRANSACTION возможен только первым оператором свежего BEGIN —
        # внутри savepoint (pytest с внешней транзакцией) PostgreSQL отклоняет
        # его ("must not be called in a subtransaction"), а упавший оператор
        # убивает транзакцию без отката к savepoint. Поэтому вместо
        # try/except вокруг заведомо мёртвого SQL режим определяется заранее,
        # деградация фиксируется в report.snapshot_isolation.
        isolation = "default_deferred"
        wrapped = connection.in_atomic_block
        with transaction.atomic():
            if connection.vendor != "postgresql":
                isolation = f"default_deferred:{connection.vendor}"
            elif wrapped:
                isolation = "default_deferred:subtransaction"
            else:
                try:
                    with connection.cursor() as cur:
                        cur.execute(SNAPSHOT_SQL)
                    isolation = "repeatable_read_read_only"
                except Exception as exc:  # свежий BEGIN: практически unreachable
                    raise CommandError(
                        f"Не удалось установить REPEATABLE READ READ ONLY: {exc}"
                    ) from exc

            options_list = _allowed_tool_type_options()  # единственное чтение options
            unknown = validate_against_taxonomy(ruleset, {o["slug"] for o in options_list})
            if unknown:
                raise CommandError(f"Slugs правил отсутствуют в allowed options: {unknown}")
            violations = check_negative_fixtures(ruleset)
            if violations:
                raise CommandError(f"Negative fixtures нарушены: {violations}")

            candidate_rules = [r for r in ruleset.rules if r.tier == TIER_CANDIDATE]
            regression_rules = [r for r in ruleset.rules if r.tier != TIER_CANDIDATE]

            predictions, collisions = [], []
            pool_ids: list[int] = []
            no_match = 0
            regression_hits = 0
            regression_collisions = 0
            per_rule = {
                r.rule_ref: {
                    "tier": r.tier,
                    "raw_hits": 0,
                    "prediction_hits": 0,
                    "collision_hits": 0,
                    "same_slug_multi_hits": 0,
                    "coverage_share": 0.0,
                }
                for r in ruleset.rules
            }
            # Товары с существующим tool_type исключаются на уровне пула и не
            # оцениваются вовсе (перезапись запрещена, rewrite_attempts всегда 0);
            # считаем их зеркальным queryset. In-loop ветка ниже — защита.
            excluded = _pool_queryset(options["pool"], has_tool_type=True).count()
            pool_qs = _pool_queryset(options["pool"])
            pool_size = pool_qs.count()
            for product in pool_qs.iterator(chunk_size=500):
                pool_ids.append(product.pk)
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
                    _tally(per_rule, verdict)
                elif verdict.status == "prediction":
                    facts_dict = {k: getattr(facts, k) for k in FACT_KEYS}
                    predictions.append(
                        {
                            "product_id": verdict.product_id,
                            "option_slug": verdict.option_slug,
                            "rule_refs": list(verdict.rule_refs),
                            "evidence": {
                                "facts": facts_dict,
                                "facts_hash": canonical_hash(facts_dict),
                                "match": verdict.evidence,
                            },
                        }
                    )
                    _tally(per_rule, verdict)
                else:
                    no_match += 1
                if regression_rules:
                    regression_verdict = evaluate_product(regression_rules, facts)
                    if regression_verdict.status == "prediction":
                        regression_hits += 1
                        _tally(per_rule, regression_verdict)
                    elif regression_verdict.status == "collision":
                        regression_collisions += 1
                        _tally(per_rule, regression_verdict)

            for metrics in per_rule.values():
                metrics["coverage_share"] = (
                    round(metrics["prediction_hits"] / pool_size, 4) if pool_size else 0.0
                )

        # --- дальше только CPU над снятыми данными ---
        ordered = sorted(predictions, key=lambda p: _sample_key(options["seed"], p["product_id"]))
        if options["sample_size"] > 0:
            selected = ordered[: options["sample_size"]]
        elif options["gate_sample_out"]:
            selected = ordered  # gate-артефакт без явного размера — все predictions
        else:
            selected = []

        finished = timezone.now()
        taxonomy_hash = _taxonomy_hash(options_list)
        report = {
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "matcher_version": MATCHER_VERSION,
            "code_sha": _code_sha(),
            "pool_filter_version": POOL_FILTER_VERSION,
            "ruleset_id": ruleset.ruleset_id,
            "ruleset_hash": ruleset.ruleset_hash,
            "taxonomy_hash": taxonomy_hash,
            "command": {
                "name": "catalog_rules_shadow",
                "args": {
                    "pool": options["pool"],
                    "ruleset": options["ruleset"],
                    "sample_size": options["sample_size"],
                    "seed": options["seed"],
                    "replay_corpus": options["replay_corpus"],
                    "out": options["out"],
                    "force": options["force"],
                    "gate_sample_out": options["gate_sample_out"],
                    "corpus": options["corpus"],
                },
            },
            "generated_at": finished.isoformat(),
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 3),
            "snapshot_isolation": isolation,
            "input_universe_hash": canonical_hash(
                {
                    "pool": options["pool"],
                    "untyped_ids": sorted(pool_ids),
                    "typed_eligible": excluded,
                }
            ),
            "pool": {
                "name": options["pool"],
                "size": pool_size,
                "typed_eligible_universe": excluded,
                "excluded_existing_tool_type": excluded,
                "rewrite_attempts": 0,
            },
            "counts": {
                "predictions": len(predictions),
                "collisions": len(collisions),
                "no_match": no_match,
                "excluded_existing_tool_type": excluded,
                "regression_tier_hits": regression_hits,
                "regression_tier_collisions": regression_collisions,
            },
            "predictions_share": round(len(predictions) / pool_size, 4) if pool_size else 0.0,
            "per_rule": dict(sorted(per_rule.items())),
            "collisions": collisions,
            "predictions": sorted(predictions, key=lambda p: p["product_id"]),
            "sample": {
                "seed": options["seed"],
                "size": len(selected),
                "product_ids": [p["product_id"] for p in selected],
            },
        }

        if options["replay_corpus"]:
            report["replay"] = self._replay(ruleset, Path(options["replay_corpus"]))

        # gate_sample валидируется ДО записи любых артефактов: отказ без
        # частично записанных файлов (P0.3).
        gate_sample = None
        if options["gate_sample_out"]:
            gate_sample = {
                "version": 1,
                "artifact": "gate_sample",
                "ruleset_hash": ruleset.ruleset_hash,
                "matcher_version": MATCHER_VERSION,
                "taxonomy_hash": taxonomy_hash,
                "seed": options["seed"],
                "pool": options["pool"],
                "pool_filter_version": POOL_FILTER_VERSION,
                "rows": [
                    {
                        "product_id": p["product_id"],
                        **p["evidence"]["facts"],
                        "facts_hash": p["evidence"]["facts_hash"],
                        "predicted_option_slug": p["option_slug"],
                        "rule_refs": p["rule_refs"],
                    }
                    for p in selected
                ],
            }
            corpus = load_corpus(Path(options["corpus"])) if options["corpus"] else None
            sample_violations = validate_gate_sample(gate_sample, corpus)
            if sample_violations:
                raise CommandError(f"gate_sample не прошёл аудит: {sample_violations}")

        out = (
            Path(options["out"])
            if options["out"]
            else _default_out_path(options["pool"], ruleset.ruleset_hash, started)
        )
        outputs = [(out, report)]
        if gate_sample is not None:
            outputs.append((Path(options["gate_sample_out"]), gate_sample))
        if not options["force"]:
            for path, _ in outputs:
                if path.exists():
                    raise CommandError(f"Файл уже существует (нужен --force): {path}")

        for path, data in outputs:
            payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
            digest = _write_atomic(path, payload)
            self.stdout.write(f"artifact={path} sha256={digest}")
        content_hash = canonical_hash(
            {k: v for k, v in report.items() if k not in VOLATILE_REPORT_KEYS}
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"pool={options['pool']} size={pool_size} "
                f"predictions={len(predictions)} collisions={len(collisions)} "
                f"report={out} content_hash={content_hash} snapshot_isolation={isolation}"
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
