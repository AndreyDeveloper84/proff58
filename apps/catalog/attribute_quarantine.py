"""Реестр карантина характеристик (трек P2).

Карантин — файловый реестр товаров, для которых движок характеристик
(``enrich_attributes``) **не должен извлекать значения**. Это замена частному
приёму «вписать имя конкретного товара в ``skip_if`` правила»: стоп-слово живёт
в правилах и потому действует на КЛАСС названий, а исключение обычно нужно для
ОДНОГО товара — с ростом пула такое стоп-слово молча гасит соседей.

Ключевые свойства контура (решения владельца, см. ``docs/catalog/attribute-quarantine.md``):

* Реестр — **файл**, не таблица: ``data/attribute_quarantine.json``. Миграций нет.
  Отсутствие файла = пустой реестр (не ошибка).
* Валидация **fail-closed до любой записи**: неизвестное поле записи, неизвестный
  ``reason``/``status``, дубль активного ``product_id``, слуг вне управляемых
  правил, битая дата — всё это отказ команды, а не пропуск записи. Опечатка
  ``atributes`` иначе молча не карантинила бы ничего.
* Запись **не удаляется** из файла: снятие карантина — ``status: "lifted"`` плюс
  ``lifted_at``/``lifted_by``. История остаётся.
* Карантин **никогда не удаляет уже записанные PAV** — только запрещает писать
  новые. Удаление — отдельная команда ``catalog_attribute_cleanup_quarantine``.

Модуль намеренно не импортирует Django: это чистый парсер/валидатор, который
можно звать из тестов и из ``conftest.py`` до инициализации приложений.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

#: Имя файла реестра внутри каталога данных.
FILENAME = "attribute_quarantine.json"

#: Единственная поддерживаемая версия формата.
VERSION = 1

# --- закрытые словари --------------------------------------------------------

REASON_OWNER_EXCLUDED = "owner_excluded"
REASON_NAME_AMBIGUOUS = "name_ambiguous"
REASON_DATA_DEFECT = "data_defect"
REASON_WRONG_TOOL_TYPE = "wrong_tool_type"
REASON_PENDING_RESEARCH = "pending_research"
REASON_RULE_DEFECT = "rule_defect"

#: Закрытый список причин. Свободный текст — в ``note``, номер задачи — в ``ticket``.
REASONS = (
    REASON_OWNER_EXCLUDED,
    REASON_NAME_AMBIGUOUS,
    REASON_DATA_DEFECT,
    REASON_WRONG_TOOL_TYPE,
    REASON_PENDING_RESEARCH,
    REASON_RULE_DEFECT,
)

#: Причины, требующие обязательной ссылки на задачу: дефект правил обязан быть
#: заведён, иначе карантин превращается в вечную заглушку без владельца.
REASONS_REQUIRING_TICKET = frozenset({REASON_RULE_DEFECT})

STATUS_ACTIVE = "active"
STATUS_LIFTED = "lifted"
STATUSES = (STATUS_ACTIVE, STATUS_LIFTED)

#: Скоуп записи.
SCOPE_PRODUCT = "product"
SCOPE_PRODUCT_ATTRIBUTE = "product+attribute"

REQUIRED_FIELDS = ("product_id", "reason", "added_at", "added_by", "status")
OPTIONAL_FIELDS = (
    "code_1c",
    "name_snapshot",
    "tool_type",
    "attributes",
    "note",
    "ticket",
    "expires_at",
    "lifted_at",
    "lifted_by",
    "lift_note",
)
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS + OPTIONAL_FIELDS)

#: Ключи верхнего уровня. ``_note`` — человеческий комментарий к файлу.
ALLOWED_TOP_LEVEL = frozenset({"version", "items", "_note"})


class QuarantineError(ValueError):
    """Ошибка формата/валидации реестра. Команды превращают её в CommandError."""


def default_registry_path(base) -> Path:
    """Путь реестра по умолчанию рядом с ``attribute_rules.json``.

    Отдельная функция (а не выражение внутри команды) нужна тестам каталога:
    ``apps/catalog/conftest.py`` подменяет её на пустой временный реестр, чтобы
    боевые записи карантина не влияли на чужие тесты.
    """
    return Path(f"{base}/{FILENAME}")


@dataclass(frozen=True)
class QuarantineEntry:
    """Одна запись реестра (уже провалидированная)."""

    product_id: int
    reason: str
    added_at: date
    added_by: str
    status: str
    attributes: tuple[str, ...] | None = None
    code_1c: str = ""
    name_snapshot: str = ""
    tool_type: str = ""
    note: str = ""
    ticket: str = ""
    expires_at: date | None = None
    lifted_at: date | None = None
    lifted_by: str = ""
    lift_note: str = ""

    @property
    def scope(self) -> str:
        return SCOPE_PRODUCT if self.attributes is None else SCOPE_PRODUCT_ATTRIBUTE

    @property
    def is_whole_product(self) -> bool:
        """True — карантин на весь товар (движок не извлекает ничего)."""
        return self.attributes is None

    def is_expired(self, today: date) -> bool:
        return self.expires_at is not None and self.expires_at < today

    def to_json(self) -> dict:
        """Представление записи для отчётов (без служебных полей)."""
        return {
            "product_id": self.product_id,
            "scope": self.scope,
            "attributes": list(self.attributes) if self.attributes is not None else None,
            "reason": self.reason,
            "ticket": self.ticket,
            "added_at": self.added_at.isoformat(),
            "added_by": self.added_by,
            "note": self.note,
        }


@dataclass
class QuarantineRegistry:
    """Загруженный реестр: записи + производные срезы."""

    path: Path
    version: int
    entries: tuple[QuarantineEntry, ...]
    today: date
    exists: bool = True
    #: product_id → действующая запись (active и не истёкшая).
    effective: dict[int, QuarantineEntry] = field(default_factory=dict)

    @property
    def active(self) -> list[QuarantineEntry]:
        return [e for e in self.entries if e.status == STATUS_ACTIVE]

    @property
    def lifted(self) -> list[QuarantineEntry]:
        return [e for e in self.entries if e.status == STATUS_LIFTED]

    @property
    def expired(self) -> list[QuarantineEntry]:
        """Активные записи с истёкшим сроком: действовать перестали, но видны."""
        return [e for e in self.active if e.is_expired(self.today)]

    @property
    def product_ids(self) -> list[int]:
        """Все упомянутые в реестре товары (включая lifted) — для проверки в БД."""
        return sorted({e.product_id for e in self.entries})

    def meta(self) -> dict:
        """Метаданные реестра для консоли/отчёта/ImportRun.stats."""
        return {
            "path": str(self.path),
            "exists": self.exists,
            "version": self.version,
            "active": len(self.active),
            "lifted": len(self.lifted),
            "expired": len(self.expired),
            "effective": len(self.effective),
        }


def _parse_date(value, entry_no: int, field_name: str) -> date:
    if not isinstance(value, str):
        raise QuarantineError(
            f"Запись #{entry_no}: поле {field_name!r} должно быть строкой-датой ISO "
            f"(YYYY-MM-DD), получено {value!r}."
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QuarantineError(
            f"Запись #{entry_no}: поле {field_name!r} — не ISO-дата (YYYY-MM-DD): "
            f"{value!r} ({exc})."
        ) from exc


def _parse_attributes(
    value, entry_no: int, managed_slugs: frozenset[str]
) -> tuple[str, ...] | None:
    """``attributes``: None (весь товар) либо непустой список известных slug'ов."""
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise QuarantineError(
            f"Запись #{entry_no}: поле 'attributes' должно быть непустым списком slug'ов "
            f"(или отсутствовать / быть null для карантина всего товара), получено {value!r}."
        )
    slugs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise QuarantineError(
                f"Запись #{entry_no}: в 'attributes' ожидается непустая строка-slug, "
                f"получено {item!r}."
            )
        slugs.append(item)
    unknown = [s for s in slugs if s not in managed_slugs]
    if unknown:
        raise QuarantineError(
            f"Запись #{entry_no}: атрибуты {sorted(unknown)} не описаны правилами "
            "(attribute_rules.json) — карантин по ним ничего бы не значил."
        )
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicates:
        raise QuarantineError(f"Запись #{entry_no}: дубли в 'attributes': {duplicates}.")
    return tuple(slugs)


def _parse_entry(raw, entry_no: int, managed_slugs: frozenset[str]) -> QuarantineEntry:
    if not isinstance(raw, dict):
        raise QuarantineError(
            f"Запись #{entry_no}: ожидался объект, получено {type(raw).__name__}."
        )

    unknown = sorted(set(raw) - ALLOWED_FIELDS)
    if unknown:
        # Опечатка вроде 'atributes' иначе молча превратила бы точечный карантин
        # в карантин всего товара (или наоборот) — поэтому fail-closed.
        raise QuarantineError(
            f"Запись #{entry_no}: неизвестные поля {unknown}. "
            f"Допустимы: {sorted(ALLOWED_FIELDS)}."
        )
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise QuarantineError(f"Запись #{entry_no}: отсутствуют обязательные поля {missing}.")

    product_id = raw["product_id"]
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
        raise QuarantineError(
            f"Запись #{entry_no}: 'product_id' должен быть положительным целым, "
            f"получено {product_id!r}."
        )

    reason = raw["reason"]
    if reason not in REASONS:
        raise QuarantineError(
            f"Запись #{entry_no} (товар {product_id}): недопустимый 'reason' {reason!r}. "
            f"Допустимы: {list(REASONS)}."
        )

    status = raw["status"]
    if status not in STATUSES:
        raise QuarantineError(
            f"Запись #{entry_no} (товар {product_id}): недопустимый 'status' {status!r}. "
            f"Допустимы: {list(STATUSES)}."
        )

    added_by = raw["added_by"]
    if not isinstance(added_by, str) or not added_by.strip():
        raise QuarantineError(
            f"Запись #{entry_no} (товар {product_id}): 'added_by' обязан быть непустой строкой."
        )

    ticket = raw.get("ticket", "")
    if not isinstance(ticket, str):
        raise QuarantineError(
            f"Запись #{entry_no} (товар {product_id}): 'ticket' обязан быть строкой."
        )
    if reason in REASONS_REQUIRING_TICKET and not ticket.strip():
        raise QuarantineError(
            f"Запись #{entry_no} (товар {product_id}): reason={reason!r} требует непустой "
            "'ticket' — дефект правил обязан быть заведён задачей."
        )

    added_at = _parse_date(raw["added_at"], entry_no, "added_at")
    expires_at = (
        _parse_date(raw["expires_at"], entry_no, "expires_at")
        if raw.get("expires_at") is not None
        else None
    )

    lifted_at = None
    lifted_by = raw.get("lifted_by", "") or ""
    if status == STATUS_LIFTED:
        if raw.get("lifted_at") is None or not str(lifted_by).strip():
            raise QuarantineError(
                f"Запись #{entry_no} (товар {product_id}): status='lifted' требует "
                "'lifted_at' и 'lifted_by' — снятие карантина обязано быть подписано."
            )
        lifted_at = _parse_date(raw["lifted_at"], entry_no, "lifted_at")
    elif raw.get("lifted_at") is not None:
        lifted_at = _parse_date(raw["lifted_at"], entry_no, "lifted_at")

    for text_field in ("code_1c", "name_snapshot", "tool_type", "note", "lift_note", "lifted_by"):
        value = raw.get(text_field, "")
        if value is not None and not isinstance(value, str):
            raise QuarantineError(
                f"Запись #{entry_no} (товар {product_id}): {text_field!r} обязан быть строкой."
            )

    return QuarantineEntry(
        product_id=product_id,
        reason=reason,
        added_at=added_at,
        added_by=added_by,
        status=status,
        attributes=_parse_attributes(raw.get("attributes"), entry_no, managed_slugs),
        code_1c=raw.get("code_1c") or "",
        name_snapshot=raw.get("name_snapshot") or "",
        tool_type=raw.get("tool_type") or "",
        note=raw.get("note") or "",
        ticket=ticket,
        expires_at=expires_at,
        lifted_at=lifted_at,
        lifted_by=lifted_by or "",
        lift_note=raw.get("lift_note") or "",
    )


def parse_registry(
    data,
    *,
    path,
    managed_slugs: Iterable[str],
    today: date | None = None,
    exists: bool = True,
) -> QuarantineRegistry:
    """Разобрать и провалидировать уже прочитанный JSON реестра (fail-closed)."""
    today = today or date.today()
    managed = frozenset(managed_slugs)

    if not isinstance(data, dict):
        raise QuarantineError(
            f"{path}: реестр карантина обязан быть объектом "
            f"{{'version': 1, 'items': [...]}}, получено {type(data).__name__}."
        )
    unknown_top = sorted(set(data) - ALLOWED_TOP_LEVEL)
    if unknown_top:
        raise QuarantineError(
            f"{path}: неизвестные ключи верхнего уровня {unknown_top}. "
            f"Допустимы: {sorted(ALLOWED_TOP_LEVEL)}."
        )
    version = data.get("version")
    if version != VERSION:
        raise QuarantineError(
            f"{path}: неподдерживаемая версия реестра {version!r} (ожидается {VERSION})."
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise QuarantineError(f"{path}: ключ 'items' обязан быть списком, получено {items!r}.")

    entries = tuple(
        _parse_entry(raw, entry_no, managed) for entry_no, raw in enumerate(items, start=1)
    )

    seen: dict[int, int] = {}
    for entry_no, entry in enumerate(entries, start=1):
        if entry.status != STATUS_ACTIVE:
            continue
        if entry.product_id in seen:
            raise QuarantineError(
                f"{path}: товар {entry.product_id} объявлен активным карантином дважды "
                f"(записи #{seen[entry.product_id]} и #{entry_no}) — какая из них "
                "действует, неизвестно."
            )
        seen[entry.product_id] = entry_no

    registry = QuarantineRegistry(
        path=Path(path),
        version=version,
        entries=entries,
        today=today,
        exists=exists,
    )
    registry.effective = {e.product_id: e for e in registry.active if not e.is_expired(today)}
    return registry


def load_registry(
    path,
    *,
    managed_slugs: Iterable[str],
    today: date | None = None,
) -> QuarantineRegistry:
    """Прочитать реестр с диска. Отсутствие файла — пустой реестр, не ошибка."""
    path = Path(path)
    if not path.exists():
        return QuarantineRegistry(
            path=path,
            version=VERSION,
            entries=(),
            today=today or date.today(),
            exists=False,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuarantineError(f"{path}: файл не разбирается как JSON — {exc}.") from exc
    return parse_registry(data, path=path, managed_slugs=managed_slugs, today=today)
