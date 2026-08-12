"""Phase 8 · ступень 2 — сборка result JSON для run fe48c2c8 (real batch 10).

Решения по каждому item — результат ручного web research (см. протокол
phase8-step2-report.md, раздел «Блок 2 — research»). Скрипт только подставляет
точные input_hash/taxonomy_hash/export_checksum из export-файла, чтобы исключить
ошибки переписывания; сами решения (identity/status/option/evidence) заданы
явно ниже и являются продуктом скилла catalog-research.
"""

from __future__ import annotations

import json
from pathlib import Path

RUN_ID = "fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6"
BASE = Path("var/catalog-processing")
EXPORT = BASE / "outbox" / f"{RUN_ID}.json"
RESULT = BASE / "inbox" / f"{RUN_ID}.result.json"
RETRIEVED = "2026-07-27T14:38:48Z"

export = json.loads(EXPORT.read_text(encoding="utf-8"))
hash_by_ref = {it["product_ref"]: it["input_hash"] for it in export["items"]}

# Общее обоснование target value: в allowed_options (300 слугов) нет
# выделенного типа «ареометр/денсиметр». Ближайший кандидат —
# izm-analizatory («Влагомеры, анализаторы, приборы»): ареометр —
# измерительный прибор. Соответствие правдоподобное, но не очевидное,
# поэтому по taxonomy-routing status="review" (identity всюду matched).
TARGET_REASON = (
    "В allowed_options нет выделенного типа «ареометр»; ближайший кандидат "
    "izm-analizatory («Влагомеры, анализаторы, приборы») — ареометр является "
    "измерительным прибором. Соответствие правдоподобное, но не очевидное: review."
)


def change(slug: str, confidence: int, evidence: list[dict], reason_code: str) -> dict:
    return {
        "target_kind": "tool_type",
        "proposed_value": {"option_slug": slug},
        "confidence": confidence,
        "reason_code": reason_code,
        "reason_detail": TARGET_REASON,
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
    # id=1 — тестовый артефакт dev-БД, идентичности в сети не существует.
    1: {
        "identity": {
            "status": "unknown",
            "article": "SMOKE-1C-001",
            "reason": "Тестовый товар «Smoke Test 1C» (артефакт smoke-тестов в dev-БД); "
            "соответствий в сети нет и быть не может.",
        },
        "status": "identity_failed",
        "reason_code": "no_real_world_identity",
        "reason_detail": "Товар — тестовый артефакт; identity gate не пройден по построению. "
        "Корректный ответ контура — отказ от предложения.",
        "changes": [],
    },
    # id=4 — Ареометр АНТ-1 (710-770) ГОСТ 18481-81.
    4: {
        "identity": {
            "status": "matched",
            "model": "АНТ-1 (710-770)",
            "reason": "Совпадение типа АНТ-1 + диапазона 710-770 + ГОСТ 18481-81 по "
            "нескольким независимым источникам (бренд отсутствует — ГОСТ-изделие).",
        },
        "status": "review",
        "reason_code": "gost_type_match",
        "reason_detail": "АНТ-1 710-770 ГОСТ 18481-81 — ареометр для нефти с термометром, "
        "шифр 111 по каталогу. Идентичность подтверждена типом+ГОСТ+диапазоном.",
        "changes": [
            change(
                "izm-analizatory",
                60,
                [
                    ev(
                        "specialized_store",
                        "https://www.rm-pro.ru/upload/iblock/8c1/8c15f95541de59d5eb5b6e5127ef5a16.pdf",
                        "Каталог лабораторной посуды rm-pro.ru (PDF)",
                        "Ареометр для нефти с термометром АНТ-1 … 111 | 710-770 | 0,5 | 500",
                    ),
                ],
                "gost_type_match",
            )
        ],
    },
    # id=5 — Ареометр АНТ-1 (830-890) ГОСТ 18481-81.
    5: {
        "identity": {
            "status": "matched",
            "model": "АНТ-1 (830-890)",
            "reason": "Совпадение типа АНТ-1 + диапазона 830-890 + ГОСТ 18481-81 (шифр 113 "
            "по каталогу rm-pro).",
        },
        "status": "review",
        "reason_code": "gost_type_match",
        "reason_detail": "АНТ-1 830-890 ГОСТ 18481-81 — ареометр для нефти с термометром, "
        "шифр 113. Идентичность подтверждена типом+ГОСТ+диапазоном.",
        "changes": [
            change(
                "izm-analizatory",
                60,
                [
                    ev(
                        "specialized_store",
                        "https://www.rm-pro.ru/upload/iblock/8c1/8c15f95541de59d5eb5b6e5127ef5a16.pdf",
                        "Каталог лабораторной посуды rm-pro.ru (PDF)",
                        "Ареометр для нефти с термометром АНТ-1 … 113 | 830-890 | 0,5 | 500",
                    ),
                ],
                "gost_type_match",
            )
        ],
    },
    # id=6 — Ареометр АНТ-2 (РФ) 750-830.
    6: {
        "identity": {
            "status": "matched",
            "model": "АНТ-2 (750-830)",
            "reason": "Совпадение типа АНТ-2 + диапазона 750-830; выпускается с поверкой РФ "
            "(pnsk-online, bioscorp).",
        },
        "status": "review",
        "reason_code": "gost_type_match",
        "reason_detail": "АНТ-2 750-830 — ареометр для нефти и нефтепродуктов с термометром. "
        "Идентичность подтверждена типом+диапазоном по нескольким источникам.",
        "changes": [
            change(
                "izm-analizatory",
                60,
                [
                    ev(
                        "specialized_store",
                        "https://www.pnsk-online.ru/catalog/mern/areometr_ant_2_750_830_830_910_990_1070_s_poverkoy_rossiya/",
                        "Ареометр АНТ-2 (750-830, 830-910, 990-1070) с поверкой — pnsk-online.ru",
                        "Ареометр АНТ-2 (750-830, 830-910, 990-1070) с поверкой, Россия — "
                        "прибор для определения плотности топлива",
                    ),
                ],
                "gost_type_match",
            )
        ],
    },
    # id=7 — Ареометр Вымпел АР-02 5002.
    7: {
        "identity": {
            "status": "matched",
            "brand": "Вымпел",
            "model": "АР-02 5002",
            "reason": "Точное совпадение brand+model: Вымпел АР-02 5002 (orionspb, "
            "vseinstrumenti).",
        },
        "status": "review",
        "reason_code": "exact_brand_model_match",
        "reason_detail": "Вымпел АР-02 — ареометр для электролита/тосола/антифриза, "
        "предел измерения 1.1–1.3 г/см³.",
        "changes": [
            change(
                "izm-analizatory",
                65,
                [
                    ev(
                        "specialized_store",
                        "https://shop.orionspb.ru/diagnost/areometry/ar02",
                        "Ареометр АР-02 — Магазин НПП «Орион»",
                        "Бренд Вымпел … Предел измерения от 1.1 до 1.3 г/см^3",
                    ),
                    ev(
                        "specialized_store",
                        "https://www.vseinstrumenti.ru/product/areometr-vympel-ar-02-5002-826031/",
                        "Ареометр Вымпел АР-02 5002 — ВсеИнструменты.ру",
                        "Ареометр Вымпел АР-02 5002 применяется для измерения плотности "
                        "электролитов в аккумуляторах",
                    ),
                ],
                "exact_brand_model_match",
            )
        ],
    },
    # id=8 — Ареометр SPARTA 549125.
    8: {
        "identity": {
            "status": "matched",
            "brand": "SPARTA",
            "article": "549125",
            "reason": "Точное совпадение артикула 549125 + бренда SPARTA (vseinstrumenti, "
            "oma.by, tssp.kz).",
        },
        "status": "review",
        "reason_code": "exact_article_match",
        "reason_detail": "SPARTA 549125 — ареометр для измерения плотности электролита.",
        "changes": [
            change(
                "izm-analizatory",
                65,
                [
                    ev(
                        "specialized_store",
                        "https://www.vseinstrumenti.ru/product/areometr-dlya-izmereniya-plotnosti-elektrolita-sparta-549125-783849/",
                        "Ареометр для измерения плотности электролита Sparta 549125 — ВсеИнструменты.ру",
                        "Преимущества ареометра SPARTA 549125 … ареометра для измерения "
                        "плотности электролита",
                    ),
                    ev(
                        "specialized_store",
                        "https://www.oma.by/areometr-dlya-izmereniya-plotnosti-elektrolita-sparta-549125-2-305907-p",
                        "Ареометр для измерения плотности электролита Sparta 549125 — ОМА",
                        "Ареометр для измерения плотности электролита Sparta 549125",
                    ),
                ],
                "exact_article_match",
            )
        ],
    },
    # id=9 — Ареометр АНТ2 830-910 с поверкой РФ.
    9: {
        "identity": {
            "status": "matched",
            "model": "АНТ-2 (830-910)",
            "reason": "Совпадение типа АНТ-2 + диапазона 830-910 + поверка РФ (5drops, "
            "izm.by, ozon).",
        },
        "status": "review",
        "reason_code": "gost_type_match",
        "reason_detail": "АНТ-2 830-910 с поверкой РФ — ареометр для нефти и нефтепродуктов "
        "с термометром.",
        "changes": [
            change(
                "izm-analizatory",
                60,
                [
                    ev(
                        "specialized_store",
                        "https://izm.by/areometr-ant-2-830-910-dlya-nefteproduktov.html",
                        "Ареометр АНТ-2 830–910 кг/м³ для нефтепродуктов с поверкой — izm.by",
                        "Ареометр с термометром АНТ-2 830-910 используются для измерения "
                        "плотности нефти и нефтепродуктов",
                    ),
                    ev(
                        "specialized_store",
                        "https://5drops.ru/product/areometr_dlya_dizelnogo_topliva_ant_2_830_910_kg_m3/",
                        "Ареометр для нефти и нефтепродуктов АНТ-2 (830…910) с поверкой — 5drops.ru",
                        "Ареометр для нефти и нефтепродуктов АНТ-2 (830...910) кг/м3, (с поверкой)",
                    ),
                ],
                "gost_type_match",
            )
        ],
    },
    # id=10 — Ареометр охлаждающей жидкости Jonnesway AR030002.
    10: {
        "identity": {
            "status": "matched",
            "brand": "Jonnesway",
            "article": "AR030002",
            "reason": "Точное совпадение артикула AR030002 на официальном сайте "
            "Jonnesway.",
        },
        "status": "review",
        "reason_code": "exact_article_match_manufacturer",
        "reason_detail": "Jonnesway AR030002 — ареометр охлаждающей жидкости (стрелочный, "
        "для антифриза), официальная карточка производителя.",
        "changes": [
            change(
                "izm-analizatory",
                70,
                [
                    ev(
                        "manufacturer",
                        "https://www.jonnesway.ru/product/4668/ar030002-areometr-ohlajdayuschey-jidkosti/",
                        "AR030002 Ареометр охлаждающей жидкости — jonnesway.ru",
                        "Ареометр охлаждающей жидкости применяется для определения "
                        "температуры кипения и замерзания охлаждающих жидкостей",
                    ),
                ],
                "exact_article_match_manufacturer",
            )
        ],
    },
    # id=11 — Ареометр универсальный KRAFT KT 835570.
    11: {
        "identity": {
            "status": "matched",
            "brand": "KRAFT",
            "article": "835570",
            "reason": "Точное совпадение артикула KT 835570 + бренда KRAFT "
            "(vseinstrumenti, illva, bossparts).",
        },
        "status": "review",
        "reason_code": "exact_article_match",
        "reason_detail": "KRAFT KT 835570 — универсальный ареометр (электролит+тосол) "
        "в пластиковой тубе с воронкой.",
        "changes": [
            change(
                "izm-analizatory",
                65,
                [
                    ev(
                        "specialized_store",
                        "https://www.vseinstrumenti.ru/product/universalnyj-areometr-kraft-elektrolit-tosol-v-plastikovoj-tube-s-voronkoj-kt-835570-1246772/",
                        "Универсальный ареометр KRAFT электролит+тосол KT 835570 — ВсеИнструменты.ру",
                        "Универсальный ареометр KRAFT электролит+тосол, в пластиковой тубе "
                        "с воронкой KT 835570",
                    ),
                    ev(
                        "specialized_store",
                        "https://illva.ru/shop/product/areometr-universalnyi-elektrolittosol-v-plasticheskoi-tube-s-voronkoi-kraft-kt-835570",
                        "Ареометр универсальный (электролит + тосол) Kraft KT 835570 — illva.ru",
                        "Бренд: KRAFT. Артикул: KT835570",
                    ),
                ],
                "exact_article_match",
            )
        ],
    },
    # id=12 — Ареометр электролита аккумулятора Jonnesway AR030001.
    12: {
        "identity": {
            "status": "matched",
            "brand": "Jonnesway",
            "article": "AR030001",
            "reason": "Модель AR030001 из наименования точно совпадает с официальной "
            "карточкой Jonnesway (048520 — код поставщика в article поле каталога).",
        },
        "status": "review",
        "reason_code": "exact_model_match_manufacturer",
        "reason_detail": "Jonnesway AR030001 — ареометр электролита аккумулятора, "
        "официальная карточка производителя.",
        "changes": [
            change(
                "izm-analizatory",
                70,
                [
                    ev(
                        "manufacturer",
                        "https://www.jonnesway.ru/product/4667/ar030001-areometr-elektrolita-akkumulyatora/",
                        "AR030001 Ареометр электролита аккумулятора — jonnesway.ru",
                        "Ареометр электролита применяется для определения плотности "
                        "электролита свинцово-цинковых аккумуляторных батарей",
                    ),
                ],
                "exact_model_match_manufacturer",
            )
        ],
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
