"""Gate-валидация human labels против gate_sample (Phase 6.0, P0.3).

Читает оба файла, проверяет labels через ``validate_gate_labels`` (sample_hash,
покрытие, enum decisions, соответствие ruleset/matcher), печатает сводку
decisions, observed precision и gate_passed. Никаких записей — ни в БД,
ни на диск.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.rules_engine import GATE_LABEL_DECISIONS, validate_gate_labels

PRECISION_GATE = 0.99
MIN_ROWS_GATE = 100


class Command(BaseCommand):
    help = "Валидация labels против gate_sample: сводка decisions, precision, gate_passed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gate-sample", type=str, required=True, help="Путь к gate_sample JSON."
        )
        parser.add_argument("--labels", type=str, required=True, help="Путь к labels JSON.")

    def handle(self, *args, **options):
        sample = json.loads(Path(options["gate_sample"]).read_text(encoding="utf-8"))
        labels = json.loads(Path(options["labels"]).read_text(encoding="utf-8"))
        violations = validate_gate_labels(labels, sample)
        if violations:
            raise CommandError("gate labels невалидны: " + "; ".join(violations))

        rows = len(sample.get("rows", []))
        decisions = Counter(lb.get("decision") for lb in labels.get("labels", []))
        correct = decisions.get("correct", 0)
        # знаменатель — все строки sample (unverifiable/taxonomy_gap тоже снижают precision)
        precision = round(correct / rows, 4) if rows else 0.0
        # collisions берётся из sample-артефакта, если поле есть (int или список)
        raw_collisions = sample.get("collisions")
        collisions = len(raw_collisions) if isinstance(raw_collisions, list) else raw_collisions
        gate_passed = (
            precision >= PRECISION_GATE
            and rows >= MIN_ROWS_GATE
            and collisions
            in (
                None,
                0,
            )
        )

        summary = " ".join(f"{d}={decisions.get(d, 0)}" for d in sorted(GATE_LABEL_DECISIONS))
        self.stdout.write(f"rows={rows} decisions: {summary}")
        self.stdout.write(f"observed_precision={precision} (correct={correct} / rows={rows})")
        gate_rule = f"precision>={PRECISION_GATE} and rows>={MIN_ROWS_GATE}"
        if collisions is not None:
            gate_rule += f" and collisions(={collisions})==0"
        self.stdout.write(f"gate_passed={'true' if gate_passed else 'false'} ({gate_rule})")
