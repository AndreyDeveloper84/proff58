"""Phase 8 · ступень 3 — сборка result JSON для run 00638eaa (real batch 20).

Решения по каждому item — результат ручного web research + ручной сверки
evidence (см. протокол phase8-step3-report.md). Скрипт только подставляет
точные input_hash/taxonomy_hash/export_checksum из export-файла; сами решения
(identity/status/option/evidence) заданы явно ниже — продукт скилла
catalog-research.
"""

from __future__ import annotations

import json
from pathlib import Path

RUN_ID = "00638eaa-0d7e-4532-b13f-ab40b3b8be0d"
BASE = Path("var/catalog-processing")
EXPORT = BASE / "outbox" / f"{RUN_ID}.json"
RESULT = BASE / "inbox" / f"{RUN_ID}.result.json"
RETRIEVED = "2026-07-28T09:05:00Z"

export = json.loads(EXPORT.read_text(encoding="utf-8"))
hash_by_ref = {it["product_ref"]: it["input_hash"] for it in export["items"]}


def change(slug: str, confidence: int, evidence: list[dict], reason_code: str,
           reason_detail: str) -> dict:
    return {
        "target_kind": "tool_type",
        "proposed_value": {"option_slug": slug},
        "confidence": confidence,
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "source": "web",
        "evidence": evidence,
    }


def ev(source_type: str, url: str, title: str, observed: str) -> dict:
    return {
        "source_type": source_type,
        "url": url,
        "title": title,
        "observed_value": observed,
        "retrieved_at": RETRIEVED,
    }


DECISIONS: dict[int, dict] = {
    # id=4 — Ареометр АНТ-1 (710-770) ц.д. 0,5 ГОСТ 18481-81.
    4: {
        "identity": {
            "status": "matched",
            "model": "АНТ-1 (710-770)",
            "reason": "Совпадение типа АНТ-1 + диапазона 710-770 + ц.д. 0,5 + ГОСТ 18481-81 "
            "(ГОСТ-изделие без бренда), независимые источники.",
        },
        "status": "researched",
        "reason_code": "gost_type_match",
        "reason_detail": "АНТ-1 710-770 ГОСТ 18481-81 — ареометр для нефти и нефтепродуктов "
        "с термометром. Тип izm-areometry («Ареометры (денсиметры)») появился в словаре "
        "(TT-01) и покрывает товар точно.",
        "changes": [
            change(
                "izm-areometry",
                90,
                [
                    ev(
                        "specialized_store",
                        "https://5drops.ru/product/areometr_dlya_nefti_i_nefteproduktov_ant_1_710_770_kg_m3/",
                        "Ареометр для нефти и нефтепродуктов АНТ-1 (710...770) кг/м³ — 5drops.ru",
                        "Вид: АНТ-1; Диапазон измерений плотности: 710-770 кг/м3; "
                        "Цена деления шкалы - 0,5 кг/м3; Произведен в соответствии с ГОСТ 18481-81",
                    ),
                ],
                "exact_taxonomy_type_available",
                "В словаре есть выделенный тип izm-areometry — точное соответствие.",
            )
        ],
    },
    # id=22 — Гайковерт ручной РГ56М.
    22: {
        "identity": {
            "status": "matched",
            "model": "РГ56М",
            "reason": "Совпадение модели РГ56М как ручного гайковёрта (механического, "
            "с мультипликатором, 3800 Н·м) по нескольким источникам.",
        },
        "status": "review",
        "reason_code": "no_exact_taxonomy_type",
        "reason_detail": "Ручной механический гайковёрт для колёс грузовых авто. В "
        "allowed_options нет типа «гаиковёрты ручные/мультипликаторы».",
        "changes": [
            change(
                "spetsialnye-klyuchi",
                55,
                [
                    ev(
                        "specialized_store",
                        "https://mitra-s.ru/products/ruchnoj-gajkovert-rg56m-s-golovkami-rg0561",
                        "Гайковерт ручной РГ56М с головками. RG.056.1. — mitra-s.ru",
                        "РГ56 Ручной гайковёрт с набором головок (для узких колес) "
                        "Момент силы 3800 Nm; Тип товара: Ручной гайковерт",
                    ),
                ],
                "no_exact_taxonomy_type",
                "Типа «ручные гайковёрты» в словаре нет; это специализированный ключ, "
                "поэтому кандидат spetsialnye-klyuchi («Специальные ключи») — "
                "правдоподобно, но не очевидно: review.",
            )
        ],
    },
    # id=123 — Домкрат кабельный ДК-5, две стойки, два винта.
    123: {
        "identity": {
            "status": "matched",
            "brand": "КВТ",
            "model": "ДК-5В",
            "reason": "Совпадение модели ДК-5 + комплектации «две стойки, два винта» "
            "по карточке производителя КВТ.",
        },
        "status": "researched",
        "reason_code": "exact_model_match_manufacturer",
        "reason_detail": "ДК-5(В) — кабельный винтовой домкрат для подъёма барабанов "
        "с кабелем. Тип domkraty («Домкраты») — прямое соответствие.",
        "changes": [
            change(
                "domkraty",
                90,
                [
                    ev(
                        "manufacturer",
                        "https://kvt-pro.ru/domkraty-kvt/domkraty-kabelnye/domkrat-kabelnyj-vintovoj-dk-5v",
                        "Домкрат кабельный винтовой ДК-5В (КВТ) — kvt-pro.ru",
                        "Домкрат кабельный винтовой КВТ ДК-5В; Комплектация ДК-5В (КВТ): "
                        "пара стоек; осевая часть домкрата ДК-5В; 2 винта",
                    ),
                ],
                "direct_type_match",
                "Кабельный домкрат — разновидность домкрата, тип domkraty покрывает точно.",
            )
        ],
    },
    # id=164 — Зарядное устройство PW 325 12В 18А (article 75552).
    164: {
        "identity": {
            "status": "matched",
            "brand": "НПП Орион",
            "model": "PW-325",
            "reason": "Совпадение модели PW 325 + параметров 12В/до 18-20А по карточке "
            "производителя НПП «Орион» (75552 — код поставщика).",
        },
        "status": "researched",
        "reason_code": "exact_model_match_manufacturer",
        "reason_detail": "Орион PW-325 — автоматическое зарядное устройство для 12В АКБ. "
        "Тип zaryadnye («Зарядные устройства») — прямое соответствие.",
        "changes": [
            change(
                "zaryadnye",
                90,
                [
                    ev(
                        "manufacturer",
                        "https://orionspb.ru/charger/7248/",
                        "Зарядное устройство НПП Орион PW-325 — orionspb.ru",
                        "Модель: Орион PW-325; Номинальное напр. АКБ, В: 12; "
                        "Максимальный зарядный ток, А: 20; Индикатор: стрелочный амперметр",
                    ),
                ],
                "direct_type_match",
                "Зарядное устройство для АКБ — тип zaryadnye покрывает точно.",
            )
        ],
    },
    # id=179 — Компрессор Бежецк АСО К-11.
    179: {
        "identity": {
            "status": "matched",
            "brand": "АСО (Бежецкий завод)",
            "model": "К-11",
            "reason": "Совпадение brand+model: Бежецкий завод АСО, поршневой компрессор "
            "К11 — карточка на официальном сайте завода.",
        },
        "status": "researched",
        "reason_code": "exact_brand_model_match_manufacturer",
        "reason_detail": "АСО К-11 — поршневой воздушный компрессор (360 л/мин, 10 атм, "
        "ресивер 60 л). Тип bp-kompressory («Компрессоры») — прямое соответствие.",
        "changes": [
            change(
                "bp-kompressory",
                90,
                [
                    ev(
                        "manufacturer",
                        "https://asobezh.ru/catalog/porshnevye_kompressory/s_privodom_2_2_4_0_kvt/gruppa_2/1030/",
                        "Поршневой компрессор К11 — Бежецкий завод АСО (asobezh.ru)",
                        "Поршневой компрессор К11/10 … произведена на базе … компрессорной "
                        "головки С412М … официального сайта Бежецкого завода АСО",
                    ),
                ],
                "direct_type_match",
                "Поршневой компрессор — тип bp-kompressory покрывает точно.",
            )
        ],
    },
    # id=377 — Шарошки победит 6 зубцов ВАЗ (article 72570).
    377: {
        "identity": {
            "status": "matched",
            "brand": "Сервис Ключ",
            "article": "72570",
            "reason": "Точное совпадение артикула 72570 + перечня применимости "
            "(ВАЗ 2101…ЗМЗ 406, 6 зубов) на сайте производителя «Сервис Ключ».",
        },
        "status": "researched",
        "reason_code": "exact_article_match_manufacturer",
        "reason_detail": "Сервис Ключ 72570 — комплект победитовых шарошек для "
        "восстановления седел клапанов ВАЗ. Тип sharoshki («Шарошки и борфрезы») — "
        "прямое соответствие.",
        "changes": [
            change(
                "sharoshki",
                95,
                [
                    ev(
                        "manufacturer",
                        "https://service-kluch.com/sharoshki-pobeditovye-vaz-2101-21011-2103-2106-21213-21083-2110-2111-zmz-406-6-zubov/",
                        "Шарошки победитовые ВАЗ 2101…ЗМЗ 406 (6 зубов) — service-kluch.com",
                        "Артикул: 72570; Тип: шарошки, зенкер; Материал кромки: победит; "
                        "Кол-во зубов: 6 шт",
                    ),
                ],
                "direct_type_match",
                "Шарошки — тип sharoshki покрывает точно.",
            )
        ],
    },
    # id=422 — Воздуходувка аккум DENZEL RB180-36 (article 59610).
    422: {
        "identity": {
            "status": "matched",
            "brand": "DENZEL",
            "model": "RB180-36",
            "article": "59610",
            "reason": "Точное совпадение brand+model+article (DZ-59610) у официального "
            "дилера DENZEL.",
        },
        "status": "researched",
        "reason_code": "exact_article_match_distributor",
        "reason_detail": "DENZEL RB180-36 — аккумуляторная воздуходувка 36В (2х18В), "
        "820 м³/ч. Тип bp-vozdukhoduvki («Воздуходувки») — прямое соответствие.",
        "changes": [
            change(
                "bp-vozdukhoduvki",
                90,
                [
                    ev(
                        "distributor",
                        "https://denzel-shop.ru/product/vozduhoduvka-akkumuljatornaja-rb180-36-li-ion-36-v-4-ach-180-kmch-820-m3ch-denzel-59610/",
                        "Воздуходувка аккумуляторная RB180-36, Li-ion, 36 В, 4 Ач — denzel-shop.ru",
                        "Воздуходувка аккумуляторная RB180-36, Li-ion, 36 В, 4 Ач, 180 км/ч, "
                        "820 м3/ч DENZEL 59610; Артикул: DZ-59610; Производитель: DENZEL",
                    ),
                ],
                "direct_type_match",
                "Воздуходувка — тип bp-vozdukhoduvki покрывает точно.",
            )
        ],
    },
    # id=1453 — Бак со станиной для швонарезчика Patriot RCS-450.
    1453: {
        "identity": {
            "status": "partial",
            "brand": "Patriot",
            "model": "RCS-450",
            "reason": "Сам швонарезчик Patriot RCS-450 подтверждён множеством источников, "
            "но отдельная запчасть «бак (для воды) со станиной» карточкой в продаже не "
            "найдена — идентичность конкретной позиции не верифицирована.",
        },
        "status": "unknown",
        "reason_code": "no_option_for_water_tank_part",
        "reason_detail": "Запчасть швонарезчика — бак для воды со станиной. В "
        "allowed_options нет подходящего типа: zap-baki — «Топливные баки» (по value "
        "не подходит — бак водяной), иных типов для баков-запчастей нет. Changes без "
        "matched identity запрещены — и их здесь и не из чего строить.",
        "changes": [],
    },
    # id=1860 — Сумка для противогаза.
    1860: {
        "identity": {
            "status": "partial",
            "reason": "Наименование generic, без бренда/модели/артикула: класс товара "
            "(сумки для противогазов ГП-5/ГП-7) подтверждается множеством листингов, "
            "конкретное изделие не верифицируется — identity gate до matched не пройден.",
        },
        "status": "unknown",
        "reason_code": "generic_name_no_model_no_option",
        "reason_detail": "Даже при matched явного типа нет: sumki-poyasnye — поясные "
        "сумки для инструмента, а сумка противогаза — аксессуар СИЗ; в siz-* типов для "
        "сумок нет.",
        "changes": [],
    },
    # id=2126 — Электрогенератор дизельный CHAMPION DS1000E (10/11кВт…).
    2126: {
        "identity": {
            "status": "partial",
            "brand": "Champion",
            "reason": "Модели «DS1000E» у Champion не существует; характеристики "
            "наименования (10/11 кВт, 17 л.с., 25 л, 170 кг) совпадают с DG10000E — "
            "вероятна опечатка 1С, exact model не подтверждён.",
        },
        "status": "unknown",
        "reason_code": "model_not_found_probable_dg10000e",
        "reason_detail": "По совокупности признаков товар — дизельный генератор Champion "
        "(тип bp-generatory был бы очевиден), но identity.status=matched недостижим "
        "из-за несуществующей модели в наименовании; changes без matched запрещены.",
        "changes": [],
    },
    # id=4944 — Бокс для инструмента для лестницы ALVE (article ALV-3003).
    4944: {
        "identity": {
            "status": "matched",
            "brand": "ALVE",
            "model": "multi box 3003",
            "article": "ALV-3003",
            "reason": "Точное совпадение brand + типа 3003 (ALV-3003) по карточкам "
            "специализированных магазинов лестниц.",
        },
        "status": "researched",
        "reason_code": "exact_article_match",
        "reason_detail": "ALVE multi box 3003 — откладной бокс для инструмента на "
        "лестницы Eurostyl/Forte, носность 3 кг. Тип yashchiki-sumki («Ящики, сумки, "
        "органайзеры») — прямое соответствие.",
        "changes": [
            change(
                "yashchiki-sumki",
                85,
                [
                    ev(
                        "specialized_store",
                        "https://www.kutil.cz/zahrada-stavba-dilna/zebriky-schudky-plosiny/doplnky-k-zebrikum/multi-box-alve-3003/",
                        "Multi box Alve 3003 — kutil.cz",
                        "Multi box Alve 3003 — praktický odkládací box k použití při práci "
                        "na žebříku … nosnost boxu: max. 3 kg … typ 3003",
                    ),
                ],
                "direct_type_match",
                "Бокс/органайзер для инструмента — тип yashchiki-sumki покрывает точно.",
            )
        ],
    },
    # id=4945 — Винт с шестигранной головкой ГОСТ Р ИСО 4017-М8х30-5,6-А2F.
    4945: {
        "identity": {
            "status": "matched",
            "model": "ГОСТ Р ИСО 4017 М8х30 5.6 А2F",
            "reason": "Совпадение стандарта (ГОСТ Р ИСО 4017) + размера (М8х30) + класса "
            "прочности (5.6) по карточке метизного поставщика (ГОСТ-изделие без бренда).",
        },
        "status": "researched",
        "reason_code": "gost_exact_match",
        "reason_detail": "Винт с шестигранной головкой с полной резьбой по ГОСТ Р ИСО "
        "4017. Тип krep-bolty («Болты и винты») — прямое соответствие.",
        "changes": [
            change(
                "krep-bolty",
                90,
                [
                    ev(
                        "specialized_store",
                        "https://rcsm-ural.ru/store/bolty/gost-r-iso-4017-2013/vint-s-shestigrannoy-golovkoy-gost-r-iso-4017-m8h30-5.6/",
                        "Винт с шестигранной головкой ГОСТ Р ИСО 4017-М8х30-5.6 — rcsm-ural.ru",
                        "Винт с шестигранной головкой ГОСТ Р ИСО 4017-М8х30-5.6; "
                        "Код: 401700216",
                    ),
                ],
                "direct_type_match",
                "Винт — тип krep-bolty («Болты и винты») покрывает точно.",
            )
        ],
    },
    # id=5312 — Адгилин М НПЭ.
    5312: {
        "identity": {
            "status": "matched",
            "brand": "Адгилин-М",
            "model": "НПЭ",
            "reason": "Совпадение brand+model: «Адгилин М НПЭ» — отражающая теплоизоляция "
            "из вспененного полиэтилена (izolon.ru и независимые продавцы).",
        },
        "status": "unknown",
        "reason_code": "no_option_for_thermal_insulation",
        "reason_detail": "Товар — фольгированная теплоизоляция (НЕ герметик: категория "
        "каталога «Герметики и монтажные пены» ошибочна). Типа «теплоизоляция» в "
        "allowed_options нет → unknown.",
        "changes": [],
    },
    # id=6503 — Боек 374432.
    6503: {
        "identity": {
            "status": "matched",
            "brand": "Hitachi/HiKOKI",
            "article": "374432",
            "reason": "Точное совпадение артикула 374432: «второй боек» (ударник) "
            "перфораторов Hitachi/HiKOKI DH24PG2/DH26PX2 и др. Категория каталога "
            "«Запчасти / ЗУБР» с брендом запчасти не совпадает — расхождение каталога.",
        },
        "status": "unknown",
        "reason_code": "no_option_for_striker_part",
        "reason_detail": "Запчасть ударного механизма перфоратора. Типа «бойки/ударники» "
        "в allowed_options нет; ближайший zap-shpindeli-valy («Шпиндели, валы, стволы, "
        "патроны») семантически про другое → unknown.",
        "changes": [],
    },
    # id=6798 — Катод (плазмотрона А141).
    6798: {
        "identity": {
            "status": "matched",
            "model": "А141 (катод)",
            "reason": "Совпадение типа расходника: катод (электрод) плазмотрона "
            "А101/А141 по нескольким сварочным поставщикам.",
        },
        "status": "review",
        "reason_code": "no_exact_taxonomy_type",
        "reason_detail": "Катод плазмотрона А141 — расходная часть для плазменной резки. "
        "Типа «электроды/катоды плазмотронов» в словаре нет.",
        "changes": [
            change(
                "svar-sopla",
                55,
                [
                    ev(
                        "specialized_store",
                        "https://teslaweld.com/elektrod-dlya-plazmotrona-a141-d20-14mm",
                        "Электрод для плазмотрона А141 (катод), D20/14мм — teslaweld.com",
                        "Электрод для плазмотрона А141 (катод) … является расходным "
                        "материалом при работе плазмотрона",
                    ),
                ],
                "no_exact_taxonomy_type",
                "Типа «катоды плазмотронов» нет; ближайший svar-sopla («Сопла, "
                "мундштуки, наконечники») — то же семейство расходки плазменной резки, "
                "но катод ≠ сопло: правдоподобно, не очевидно → review.",
            )
        ],
    },
    # id=10559 — Беспроводной сканер штрих-кода.
    10559: {
        "identity": {
            "status": "partial",
            "reason": "Наименование generic, без бренда/модели/артикула: класс товара "
            "существует, конкретное изделие не верифицируется.",
        },
        "status": "unknown",
        "reason_code": "generic_name_no_option",
        "reason_detail": "Сканер штрих-кода — торговое/кассовое оборудование, не "
        "инструмент: в allowed_options подходящего типа нет (категория каталога "
        "«Измерительный инструмент» спорная).",
        "changes": [],
    },
    # id=11232 — Паяльник REXANT 12-0621 65Вт 5 жал.
    11232: {
        "identity": {
            "status": "matched",
            "brand": "REXANT",
            "article": "12-0621",
            "reason": "Точное совпадение brand+article: REXANT 12-0621 (паяльник 65Вт "
            "с регулировкой, 5 жал).",
        },
        "status": "researched",
        "reason_code": "exact_article_match",
        "reason_detail": "REXANT 12-0621 — одиночный паяльник с цифровой регулировкой "
        "и набором жал (не паяльная станция) → payalniki, а не payalniki-stancii.",
        "changes": [
            change(
                "payalniki",
                90,
                [
                    ev(
                        "specialized_store",
                        "https://rexant-shop.ru/product/rexant-12-0621/126490",
                        "Rexant 12-0621 Набор для пайки (паяльник 65Вт, 200-500°C, "
                        "подставка, 5 жал) — rexant-shop.ru",
                        "Потребляемая мощность: 65 Вт; Комплектация: паяльник, подставка, "
                        "5 жал разных типов",
                    ),
                ],
                "direct_type_match",
                "Одиночный паяльник — тип payalniki покрывает точно.",
            )
        ],
    },
    # id=23606 — Автомат SP pius п/э пакет 3кг.
    23606: {
        "identity": {
            "status": "matched",
            "brand": "SP plus (Эконом)",
            "reason": "Совокупность сигналов: «Автомат SP» + «п/э пакет 3кг» = "
            "стиральный порошок «SP plus Эконом» автомат, 3 кг, п/э пакет («pius» — "
            "опечатка в наименовании 1С).",
        },
        "status": "review",
        "reason_code": "name_typo_indirect_identity",
        "reason_detail": "Товар — стиральный порошок (бытовая химия); категория "
        "каталога «Электрика и освещение» ошибочна. Тип hoz-himiya правдоподобен, но "
        "identity выведена косвенно (через опечатку) → review.",
        "changes": [
            change(
                "hoz-himiya",
                65,
                [
                    ev(
                        "specialized_store",
                        "https://u2b.ru/catalog/bytovaya_khimiya/sredstva_dlya_stirki/poroshok_stiralnyy_avtomat_sp_plus_ekonom_universal_3kg/",
                        "Порошок стиральный автомат «SP plus Эконом» универсал 3кг — u2b.ru",
                        "Порошок стиральный автомат \"SP plus Эконом\" универсал 3кг; "
                        "Назначение: Для стирки",
                    ),
                ],
                "name_typo_indirect_identity",
                "Стиральный порошок = бытовая химия → hoz-himiya; уверенность снижена "
                "из-за косвенной идентификации (опечатка pius/plus): review.",
            )
        ],
    },
    # id=28270 — Долг за инструмент.
    28270: {
        "identity": {
            "status": "unknown",
            "reason": "Не товар: служебная запись «Долг за инструмент» (категория "
            "«Не на сайте / Офис»). Идентичности в сети не существует и быть не может.",
        },
        "status": "identity_failed",
        "reason_code": "not_a_product",
        "reason_detail": "Позиция — учётная запись долга, а не товар; identity gate не "
        "пройден по построению. Корректный ответ контура — отказ.",
        "changes": [],
    },
    # id=39029 — Агар Чапека-Докса для грибов, гранулированная форма (article CM075-500G).
    39029: {
        "identity": {
            "status": "partial",
            "brand": "HiMedia",
            "model": "Czapek Dox Agar, granulated, 500g",
            "reason": "По совокупности (название + «гранулированная форма» + 500 г) это "
            "HiMedia GM075-500G; артикул в БД CM075-500G расходится на одну букву "
            "(C≠G) — до matched не дотягивает.",
        },
        "status": "unknown",
        "reason_code": "no_option_lab_medium_not_a_tool",
        "reason_detail": "Микробиологическая питательная среда — не инструмент и не "
        "хозтовар из словаря: подходящего типа в allowed_options нет → unknown.",
        "changes": [],
    },
}

items = []
for ref in sorted(DECISIONS):
    d = DECISIONS[ref]
    item = {
        "product_ref": ref,
        "input_hash": hash_by_ref[ref],
        "identity": d["identity"],
        "status": d["status"],
        "reason_code": d["reason_code"],
        "reason_detail": d["reason_detail"],
    }
    if d["changes"]:
        item["changes"] = d["changes"]
    items.append(item)

result = {
    "schema_version": "1.0",
    "run_id": RUN_ID,
    "taxonomy_hash": export["taxonomy_hash"],
    "export_checksum": export["checksum"],
    "items": items,
}
RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written: {RESULT} items={len(items)}")
print("refs covered:", sorted(DECISIONS) == sorted(hash_by_ref))
