"""Подбор доноров для обрезанных названий внутри самого каталога.

1С обрезала часть наименований ровно по 50 символов, но названия в каталоге
шаблонные: «Плашка М 6х0,5 класс точности 6g, сталь 9ХС, ГОСТ 9740-71» — и у
части позиций той же серии имя в лимит уложилось. Такой уцелевший сосед и есть
донор: его хвост достраивает обрезанного собрата, не требуя внешних источников.

Совпадение ищется по «скелету» — названию, в котором числа и размеры заменены
плейсхолдером. Донор принимается, только если он начинается ровно с обрезанной
строки: иначе это другая позиция, а не та же серия.

Команда ничего не пишет. Она готовит CSV для ``catalog_restore_names``:

    catalog_name_analogs --out var/analogs.csv
    catalog_restore_names --file var/analogs.csv          # посмотреть
    catalog_restore_names --file var/analogs.csv --commit
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.catalog.models import Product

# Длина, на которой 1С обрубила наименование.
CUT_LENGTH = 50
# Уверенность инференса: хвост взят из данных, но донор мог отличаться деталью,
# поэтому ниже, чем у найденной карточки производителя.
CONFIDENCE = 0.75

_NUMBERS = re.compile(r"[0-9][0-9.,хx/-]*")
_SPACES = re.compile(r"\s+")
# Буквенный префикс артикула: «GR7MD18022» → «GR», «SK-TGP18025» → «SK-TGP».
# Внутри такого префикса лежит одна серия производителя, и хвосты у неё общие.
_ARTICLE_PREFIX = re.compile(r"^[A-Za-zА-Яа-я][A-Za-zА-Яа-я-]*")

# Хвост с характеристикой переносить нельзя: у «Трансформатор НТС-1,6У2 … 1,6кВА
# 320х245х355мм 35кг» мощность, габариты и вес свои у каждой модели, и донор
# соседней модели подставил бы чужие. Номер стандарта («ГОСТ 9740-71») и марка
# стали единиц измерения не содержат, поэтому под правило не попадают.
_MEASURED_TAIL = re.compile(
    r"\d[\d.,х/xX-]*\s*(кВА|кВт|Вт|кг|гр|мм|см|мл|мАч|Ач|А/ч|В|л|об/мин|Нм|Дж)\b",
    re.IGNORECASE,
)


def skeleton(name: str) -> str:
    """Название без чисел и размеров: «Плашка М 6х0,5 класс…» → «Плашка М # класс…»."""
    return _SPACES.sub(" ", _NUMBERS.sub("#", name)).strip()


def _article_prefix(article: str) -> str:
    """Буквенная часть артикула — метка серии производителя."""
    match = _ARTICLE_PREFIX.match((article or "").strip())
    return match.group(0).upper() if match else ""


class Command(BaseCommand):
    help = "Подобрать доноров для обрезанных названий среди уцелевших позиций каталога."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="куда положить CSV с кандидатами")
        parser.add_argument(
            "--in-stock",
            action="store_true",
            help="только позиции на остатках — их видит покупатель сегодня",
        )

    def handle(self, *args, **options):
        queryset = Product.objects.only(
            "id", "name", "original_name", "content_field_sources"
        ).order_by("id")
        if options["in_stock"]:
            queryset = queryset.filter(available_quantity__gt=0)

        cut: list[Product] = []
        donors: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for product in Product.objects.only(
            "id", "name", "original_name", "article", "content_field_sources"
        ).iterator(chunk_size=1000):
            name_source = (product.content_field_sources or {}).get("name", "")
            # Донором может быть и позиция с обрезанной строкой 1С — если её имя
            # уже восстановлено по карточке производителя. Так один найденный
            # представитель серии закрывает всех остальных: нашли «Бур … цельный
            # твердосплавный» — и десяток собратьев достраивается без поиска.
            # Достройки по аналогу (inferred) донорами не становятся: иначе одна
            # ошибка расползлась бы по цепочке.
            if len(product.original_name or "") == CUT_LENGTH and name_source != "web":
                continue
            # Индексируем по скелету первых слов: обрезанное имя короче донора,
            # и полный скелет у них никогда не совпадёт.
            words = product.name.split()
            for length in range(2, min(len(words), 12)):
                key = " ".join(_NUMBERS.sub("#", w) for w in words[:length])
                donors[key].append((product.name, _article_prefix(product.article)))

        for product in queryset.iterator(chunk_size=1000):
            if len(product.original_name or "") != CUT_LENGTH:
                continue
            if (product.content_field_sources or {}).get("name"):
                continue  # имя уже восстановлено — второй раз не трогаем
            cut.append(product)

        rows = []
        skipped = 0
        for product in cut:
            candidate = self._pick(product, donors)
            if candidate is None:
                skipped += 1
                continue
            rows.append(candidate)

        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["product_id", "name", "evidence_url", "confidence", "source"])
            writer.writerows(rows)

        self.stdout.write(f"обрезанных без имени из внешнего источника: {len(cut)}")
        self.stdout.write(self.style.SUCCESS(f"донор найден:  {len(rows)}"))
        self.stdout.write(f"донора нет:    {skipped}  ← остаётся поиск в интернете")
        self.stdout.write(f"файл: {out}")

    def _pick(self, product: Product, donors: dict[str, list[tuple[str, str]]]) -> list | None:
        """Донор той же серии; числа берём свои, хвост — от донора.

        Сравнивать строки напрямую нельзя: у донора другой типоразмер, и
        «Плашка М 6х0,5 …» не является префиксом «Плашка М 30х2,0 …». Поэтому
        сопоставляем послово, заменив числа плейсхолдером, а последнее слово
        обрезанного имени отбрасываем — 1С разрубила его посередине.
        """
        words = product.name.split()
        if len(words) < 3:
            return None
        # 1С рубит по символам, а не по словам: обрыв приходится либо на середину
        # слова («… ГОС»), либо ровно на пробел — тогда последнее слово целое, и
        # отбрасывать его не нужно. Пробуем оба разбиения.
        for head, cut_word in ((words[:-1], words[-1]), (words, "")):
            candidate = self._pick_for(product, donors, head, cut_word)
            if candidate is not None:
                return candidate
        return None

    def _pick_for(
        self,
        product: Product,
        donors: dict[str, list[tuple[str, str]]],
        head: list[str],
        cut_word: str,
    ) -> list | None:
        head_pattern = [_NUMBERS.sub("#", word) for word in head]

        prefix = _article_prefix(product.article)
        tails: dict[str, str] = {}
        same_series: dict[str, str] = {}
        for donor_name, donor_prefix in donors.get(" ".join(head_pattern), []):
            donor_words = donor_name.split()
            if len(donor_words) <= len(head):
                continue
            donor_pattern = [_NUMBERS.sub("#", word) for word in donor_words[: len(head)]]
            if donor_pattern != head_pattern:
                continue
            tail_words = donor_words[len(head) :]
            # Обрубок должен быть началом первого слова хвоста: «ГОС» → «ГОСТ».
            # Иначе это другая серия, просто похожая по скелету. Пустой обрубок
            # (обрыв пришёлся на пробел) подходит к любому хвосту.
            if cut_word and not tail_words[0].lower().startswith(cut_word.lower()):
                continue
            tail = " ".join(tail_words)
            if _MEASURED_TAIL.search(tail):
                continue  # хвост описывает саму позицию, а не серию
            tails[tail] = donor_name
            if prefix and donor_prefix == prefix:
                same_series[tail] = donor_name

        # Артикул точнее скелета: у кругов SKYWER «SK-TGP…» и MD-STARS «GR7MD…»
        # хвост свой у каждой серии, и по одному лишь названию их не развести.
        if len(tails) > 1 and len(same_series) == 1:
            tails = same_series

        if not tails:
            return None

        # Несколько вариантов хвоста — ещё не конфликт: «сталь Р6М5К5» и «сталь
        # Р6М5К5, ГОСТ 10902» описывают одно и то же, второй просто подробнее.
        # Берём самый полный, если остальные — его начало.
        longest = max(tails, key=len)
        if any(not longest.startswith(tail) for tail in tails):
            # А вот это настоящий конфликт: у молотка ЗУБР с бойком 35 мм вес
            # 450 г, у 47 мм — 680 г, и какой из них наш, по названию не понять.
            # Чужое число в карточке хуже, чем обрыв.
            return None

        tail, donor_name = longest, tails[longest]
        restored = " ".join(head + [tail])
        if restored == product.name:
            return None
        return [product.pk, restored, f"донор: {donor_name}", CONFIDENCE, "inferred"]
