"""Gate-валидация human labels против gate_sample (Phase 6.0, P0.3).

Читает оба файла, проверяет labels через ``validate_gate_labels`` (sample_hash,
покрытие, enum decisions, соответствие ruleset/matcher), печатает сводку
decisions, observed precision и gate_passed. Никаких записей — ни в БД,
ни на диск.

Hotfix post-#579 (fail-closed): sample без ``corpus_overlap_checked: true``
или без ``collision_count == 0`` gate НЕ проходит — violation в выводе,
``gate_passed=false`` и ненулевой выход (CommandError).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.rules_engine import GATE_LABEL_DECISIONS, validate_gate_labels

PRECISION_GATE = 0.99
MIN_ROWS_GATE = 100


def _load_json(path: Path, kind: str):
    """Чтение входного JSON: отсутствующий файл, не-UTF8 или битый JSON —
    CommandError с понятным сообщением (стиль как у queue_import._load_json)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise CommandError(f"Файл не найден ({kind}): {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"Невалидный JSON ({kind}): {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CommandError(f"Файл не UTF-8 ({kind}): {exc}") from exc


class Command(BaseCommand):
    help = "Валидация labels против gate_sample: сводка decisions, precision, gate_passed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gate-sample", type=str, required=True, help="Путь к gate_sample JSON."
        )
        parser.add_argument("--labels", type=str, required=True, help="Путь к labels JSON.")

    def handle(self, *args, **options):
        sample = _load_json(Path(options["gate_sample"]), "gate_sample")
        labels = _load_json(Path(options["labels"]), "labels")
        violations = validate_gate_labels(labels, sample)
        if violations:
            raise CommandError("gate labels невалидны: " + "; ".join(violations))

        # fail-closed аудит sample-артефакта (review post-#579): отсутствие
        # полей или недопустимые значения трактуются как НЕпрохождение gate,
        # а не как допустимое состояние
        sample_violations = []
        if sample.get("corpus_overlap_checked") is not True:
            sample_violations.append(
                "corpus_overlap_checked is not true: пересечение sample ∩ training "
                "corpus не проверено (неофициальный sample)"
            )
        collision_count = sample.get("collision_count")
        if collision_count is None:
            sample_violations.append("обязательное поле collision_count отсутствует")
        elif collision_count != 0:
            sample_violations.append(f"collision_count={collision_count} != 0")

        rows = len(sample.get("rows", []))
        decisions = Counter(lb.get("decision") for lb in labels.get("labels", []))
        correct = decisions.get("correct", 0)
        # знаменатель — все строки sample (unverifiable/taxonomy_gap тоже снижают precision)
        precision = correct / rows if rows else 0.0
        # gate по НЕокруглённому precision; округление — только для вывода
        gate_passed = (
            precision >= PRECISION_GATE and rows >= MIN_ROWS_GATE and not sample_violations
        )

        summary = " ".join(f"{d}={decisions.get(d, 0)}" for d in sorted(GATE_LABEL_DECISIONS))
        self.stdout.write(f"rows={rows} decisions: {summary}")
        self.stdout.write(
            f"observed_precision={round(precision, 4)} (correct={correct} / rows={rows})"
        )
        for violation in sample_violations:
            self.stdout.write(f"violation: {violation}")
        gate_rule = (
            f"precision>={PRECISION_GATE} and rows>={MIN_ROWS_GATE} "
            "and collision_count==0 and corpus_overlap_checked"
        )
        self.stdout.write(f"gate_passed={'true' if gate_passed else 'false'} ({gate_rule})")
        if sample_violations:
            raise CommandError(
                "gate sample не прошёл fail-closed аудит: " + "; ".join(sample_violations)
            )
