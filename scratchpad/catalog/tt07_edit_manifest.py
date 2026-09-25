"""TT-07 · правка canonical manifest: +5 опций, пересчёт обоих хэшей, валидация.

Состав утверждён владельцем 2026-07-28 (переписка TT-07):
svar-katody, gaikoverty-ruchnye, zap-boyki, gaikovery, bp-leska.

Вставка — в алфавитную позицию по slug (как izm-areometry в TT-01).
Формат файла сохраняется: json indent=2, ensure_ascii=False, '\n' в конце.
После записи — fail-closed проверка load_manifest().
"""

from __future__ import annotations

import io
import json

from apps.catalog.taxonomy_manifest import (
    load_manifest,
    manifest_semantic_hash,
    taxonomy_identity_hash,
)

PATH = "data/catalog_processing_rules/tool_type_taxonomy.v1.json"

NEW = [
    {
        "slug": "bp-leska",
        "value": "Леска триммерная",
        "sort_order": 17,
        "origin_kind": "manual_backport",
        "origin_ref": "phase8 step3 + owner decision 2026-07-28 (TT-07)",
        "review_status": "approved",
        "review_reason": "193 SKU лески свалены в prochaya-osnastka (свалка, не тип); bp-trimmery — машины, bp-cepi — цепи пил, hoz-lezviya — металлические лезвия. Крупнейшая ниша пакета (214 SKU).",
        "review_ref": "tt-07",
        "legacy_aliases": [],
    },
    {
        "slug": "gaikoverty",
        "value": "Гайковёрты",
        "sort_order": 19,
        "origin_kind": "manual_backport",
        "origin_ref": "phase8 step3 + owner decision 2026-07-28 (TT-07)",
        "review_status": "approved",
        "review_reason": "108 сетевых/аккумуляторных гайковёртов ошибочно лежат в dreli-shurupoverty (ударный механизм + квадрат под головку, не патрон под сверло); bp-pnevmogaikoverty — пневмо. Решение владельца: value без скобок — класс разводят соседние типы.",
        "review_ref": "tt-07",
        "legacy_aliases": [],
    },
    {
        "slug": "gaikoverty-ruchnye",
        "value": "Гайковёрты ручные",
        "sort_order": 20,
        "origin_kind": "manual_backport",
        "origin_ref": "phase8 step3 + owner decision 2026-07-28 (TT-07)",
        "review_status": "approved",
        "review_reason": "Ручной гайковёрт — редуктор-мультипликатор (не гаечный ключ, не динамометрический, не вороток, не пневмо); spetsialnye-klyuchi — зонтик (ст. 3, товар 22). Ниша ~6 SKU.",
        "review_ref": "tt-07",
        "legacy_aliases": [],
    },
    {
        "slug": "svar-katody",
        "value": "Катоды (электроды) плазмотронов",
        "sort_order": 11,
        "origin_kind": "manual_backport",
        "origin_ref": "phase8 step3 + owner decision 2026-07-28 (TT-07)",
        "review_status": "approved",
        "review_reason": "Катод — эмиссионный элемент плазмотрона: не сопло (газодинамика), не цанга (TIG), не MMA-электрод (плавящийся). Модерация ст. 3 отклонила катод А141 в svar-sopla (товар 6798). Перебор всех 15 svar-* — §предложение TT-07.",
        "review_ref": "tt-07",
        "legacy_aliases": [],
    },
    {
        "slug": "zap-boyki",
        "value": "Бойки и ударники",
        "sort_order": 21,
        "origin_kind": "manual_backport",
        "origin_ref": "phase8 step3 + owner decision 2026-07-28 (TT-07)",
        "review_status": "approved",
        "review_reason": "Боек — свободный ударный элемент ударного механизма перфоратора: не шпиндель/вал/ствол (zap-shpindeli-valy), не поршневая группа, не оснастка (piki-dolota), не пневмо (bp-osnastka-pnevmomolotkov). Ниша ~17 SKU (ст. 3, товар 6503).",
        "review_ref": "tt-07",
        "legacy_aliases": [],
    },
]

with io.open(PATH, encoding="utf-8") as fh:
    doc = json.load(fh)

old_identity = doc["taxonomy_identity_hash"]
old_semantic = doc["manifest_semantic_hash"]
options = doc["options"]
assert len(options) == 329, f"ожидалось 329 опций, факт {len(options)}"
existing = {o["slug"] for o in options}
for o in NEW:
    assert o["slug"] not in existing, f"{o['slug']} уже есть"

options.extend(NEW)
options.sort(key=lambda o: o["slug"])

doc["taxonomy_identity_hash"] = taxonomy_identity_hash(options)
doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)

text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
with io.open(PATH, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)

m = load_manifest()
print("options:", len(m.options))
print("identity:", old_identity[:12], "->", m.identity_hash[:12])
print("semantic:", old_semantic[:12], "->", m.semantic_hash[:12])
print("identity_full:", m.identity_hash)
print("semantic_full:", m.semantic_hash)
print("MANIFEST_VALID")
