"""Восстановление обрезанных названий по данным, найденным в интернете.

1С отдала часть номенклатуры с наименованием, обрезанным ровно по 50 символов
(6 164 позиции на стенде, из них 489 на остатках). Хвост потерян в самой учётной
системе — восстановить его можно только из внешнего источника: карточки
производителя, дистрибьютора или магазина, найденной по артикулу.

Команда принимает готовый разбор — файл с парами «товар → полное название» и
ссылкой на источник — и применяет его штатным механизмом
``provenance.apply_sourced_value`` с ``source="web"``. Тот сверяет baseline
(если имя успели поправить руками после подготовки файла — ``conflict``),
уважает приоритет источников (ручной контент не затирается) и проставляет
``content_field_sources['name'] = 'web'``.

Формат файла — CSV с заголовком:

    product_id,name,evidence_url,confidence,source
    633,"Пылесос Hitachi R14DSL 14В аккумуляторный без аккумулятора",https://…,0.9,web

Источников два. ``web`` — карточка производителя или магазина, ссылка обязательна.
``inferred`` — достройка по позиции-донору из этого же каталога: у шаблонных
названий («Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71») часть
позиций уцелела, и хвост берётся из них, а не из головы. У инференса приоритет
ниже (10 против 25), поэтому веб-находка его потом перекроет.

``original_name`` не трогается никогда: там лежит то, что прислала 1С.

Порядок:

    catalog_restore_names --file var/names.csv              # dry-run по умолчанию
    catalog_restore_names --file var/names.csv --commit
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog import provenance
from apps.catalog.models import Product

# Ниже этого порога уверенности предложение не применяем: восстановленное имя
# видит покупатель, и «примерно похоже» здесь не годится.
MIN_CONFIDENCE = 0.7
NAME_MAX = 512


class Command(BaseCommand):
    help = "Применить найденные в интернете полные названия к обрезанным позициям."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", required=True, help="CSV: product_id,name,evidence_url,confidence"
        )
        parser.add_argument(
            "--allow-equal",
            action="store_true",
            help=(
                "Разрешить перезапись имени, ранее найденного тем же способом (source=web). "
                "Без флага повторная правка блокируется приоритетом — это защита от "
                "случайного перетирания уже проверенного результата."
            ),
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Записать. Без флага — только показать, что произойдёт.",
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"файл не найден: {path}")

        rows = self._read(path)
        stats: dict[str, int] = {}
        for row in rows:
            outcome = self._apply(row, commit=options["commit"], allow_equal=options["allow_equal"])
            stats[outcome] = stats.get(outcome, 0) + 1

        self.stdout.write("")
        for outcome, count in sorted(stats.items(), key=lambda pair: -pair[1]):
            style = self.style.SUCCESS if outcome == "applied" else self.style.WARNING
            self.stdout.write(style(f"{outcome:<18} {count}"))
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("\n--dry-run: в базу ничего не записано."))

    def _read(self, path: Path) -> list[dict]:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        required = {"product_id", "name", "evidence_url", "confidence"}
        for index, row in enumerate(rows, start=2):
            missing = required - set(row)
            if missing:
                raise CommandError(f"строка {index}: нет колонок {sorted(missing)}")
            source = (row.get("source") or "web").strip()
            if source not in {"web", "inferred"}:
                raise CommandError(f"строка {index}: source должен быть web или inferred")
            evidence = (row.get("evidence_url") or "").strip()
            if source == "web" and not evidence.startswith("https://"):
                raise CommandError(f"строка {index}: для source=web нужна https-ссылка")
            # У инференса ссылки нет, но донор обязателен: иначе не проверить,
            # откуда взялся хвост.
            if source == "inferred" and not evidence:
                raise CommandError(
                    f"строка {index}: для source=inferred укажите донора в evidence_url"
                )
        return rows

    def _apply(self, row: dict, *, commit: bool, allow_equal: bool = False) -> str:
        product_id = int(row["product_id"])
        name = (row["name"] or "").strip()
        confidence = float(row["confidence"] or 0)
        source = (row.get("source") or "web").strip()

        if not name or len(name) > NAME_MAX:
            return "invalid_name"
        if confidence < MIN_CONFIDENCE:
            return "low_confidence"

        product = (
            Product.objects.filter(pk=product_id)
            .only("id", "name", "content_field_sources")
            .first()
        )
        if product is None:
            return "missing_product"
        if product.name == name:
            return "already_same"

        if not commit:
            self.stdout.write(f"  было:  {product.name}")
            self.stdout.write(self.style.SUCCESS(f"  стало: {name}"))
            self.stdout.write("")
            return "would_apply"

        command = provenance.SourcedValueCommand(
            product_id=product_id,
            target_kind="name",
            attribute_slug="",
            value={"type": "text", "value": name},
            source=source,
            confidence=confidence,
            observed_value_hash=provenance.value_hash(product.name or ""),
            observed_source=(product.content_field_sources or {}).get("name", ""),
            allow_equal_override=allow_equal,
        )
        with transaction.atomic():
            result = provenance.apply_sourced_value(command)
        return result.status
