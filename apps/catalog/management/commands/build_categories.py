"""Построение дерева категорий сайта из ``group_mapping.json`` (ADR-0002).

Дерево категорий — мастер на сайте; связь с 1С только по ``external_id``.
Дерево строится из ``site_path`` маппинга, а НЕ из ``tool_type_rules.json``.

Идемпотентно: повторный запуск не плодит дубли (узлы ищутся по имени в рамках
родителя). Группы ``on_site: false`` размещаются под скрытым корнем «Не на сайте».
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.ingest import load_group_mapping
from apps.catalog.models import Category

OFFSITE_ROOT_NAME = "Не на сайте"

# Транслитерация для ЧПУ-слугов категорий (латиница, как у tool_type-слугов):
# /catalog/elektroinstrument/, а не /catalog/электроинструмент/.
_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) for ch in text.lower())


def _unique_slug(name: str) -> str:
    """Глобально уникальный латинский slug категории (имена ветвятся, slug — нет)."""
    base = slugify(transliterate(name)) or "kategoriya"
    slug = base
    n = 2
    while Category.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Command(BaseCommand):
    help = "Создать дерево Category из data/group_mapping.json (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с group_mapping.json")

    def handle(self, *args, **options):
        mapping = load_group_mapping(options["path"])
        created = {"count": 0}

        with transaction.atomic():
            for row in mapping:
                on_site = bool(row.get("on_site"))
                site_path = list(row.get("site_path") or [])
                external_id = str(row["external_id"])

                if on_site and site_path:
                    leaf = self._ensure_path(site_path, on_site=True, created=created)
                else:
                    # on_site:false или пустой site_path → под скрытый корень, листом по group_1c
                    offsite_root = self._ensure_node(
                        None, OFFSITE_ROOT_NAME, on_site=False, created=created
                    )
                    leaf = self._ensure_node(
                        offsite_root,
                        row.get("group_1c") or external_id,
                        on_site=False,
                        created=created,
                    )

                self._set_external_id(leaf, external_id)

        total = Category.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Категории: создано {created['count']}, всего в дереве {total}, "
                f"верхнего уровня на сайте {Category.objects.filter(depth=1, on_site=True).count()}."
            )
        )
        return str(created["count"])

    def _ensure_path(self, names: list[str], *, on_site: bool, created: dict) -> Category:
        parent: Category | None = None
        for name in names:
            parent = self._ensure_node(parent, name, on_site=on_site, created=created)
        return parent  # последний = лист

    def _ensure_node(
        self, parent: Category | None, name: str, *, on_site: bool, created: dict
    ) -> Category:
        name = name.strip()
        existing = self._find_child(parent, name)
        if existing is not None:
            return existing

        defaults = dict(
            name=name,
            slug=_unique_slug(name),
            on_site=on_site,
            is_active=on_site,
        )
        if parent is None:
            node = Category.add_root(**defaults)
        else:
            node = parent.add_child(**defaults)
        created["count"] += 1
        return node

    @staticmethod
    def _find_child(parent: Category | None, name: str) -> Category | None:
        if parent is None:
            return Category.objects.filter(depth=1, name=name).first()
        return parent.get_children().filter(name=name).first()

    @staticmethod
    def _set_external_id(leaf: Category, external_id: str) -> None:
        """Проставить external_id_1c листу. Поле unique — при дубле site_path
        (две группы 1С → один лист) код остаётся за первой группой, остальные
        резолвятся к этому листу по site_path при импорте товаров."""
        if leaf.external_id_1c == external_id:
            return
        if leaf.external_id_1c:
            return  # уже занят другой группой 1С — это ожидаемый дубль маппинга
        if Category.objects.filter(external_id_1c=external_id).exists():
            return
        leaf.external_id_1c = external_id
        leaf.save(update_fields=["external_id_1c"])
