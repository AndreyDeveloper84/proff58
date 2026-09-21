# PF-SH-BLOCKERS-01 — backlog 11 блокеров перфораторов и шлифмашин

**Статус:** backlog, **не запущен** (OWNER DECISION PF-SH-RELEASE-01 §26: только после BURY-MEDIA-PILOT-01).
**Источник:** `docs/catalog/appendix/2026-09-21-pf-sh-release-gate-01/pf-sh-release-blockers.json`
(manifest sha256 `112281b5…c866c`).

Выпуск (PF-SH-RELEASE-01) открыл 74 из 85 commercial SKU. Эти 11 остаются `noindex` и вне sitemap.
Исправленный SKU попадает в индекс **только новым гейтом** (повторная проверка SKU и правка
`data/seo/indexable_products.json` через PR). Само исправление данных индекс не меняет.

## Очередь по стоимости

| # | SKU | Товар | Блокер | Действие | Класс | Цена |
|---|---|---|---|---|---|---|
| 1 | 45125 | HiKOKI SB8V2 (ленточная, 1020 Вт) | CHARACTERISTICS | удалить ошибочный PAV `voltage=8` (source=regex, «8» из модели) | DATA | 1 PAV |
| 2 | 45450 | РЕСАНТА ЭШМ-125/5Э | CHARACTERISTICS (0 характеристик) | карточка resanta.ru существующим парсером (`75/6/3`) → `catalog_import_scraped` | DATA | парсер есть |
| 3 | 45452 | РЕСАНТА ЭШМ-125Э | CHARACTERISTICS (0 характеристик) | то же (`75/6/2`) | DATA | парсер есть |
| 4 | 45113 | Интерскол ПШВ-115/300ЭМ | CHARACTERISTICS (0), нет артикула | карточка interskol.ru по модели | DATA | парсер есть, identity по модели |
| 5 | 44955 | ЗУБР ЗШС-330 (ленточно-дисковый станок) | TAXONOMY | перетипизация в `stanki-zatochnye` / `tochila-nazhdaki` — **решение владельца** | TAXONOMY | 1 SKU |
| 6 | 45339 | WORTEX AG 1210-1 | MEDIA + PRODUCT_IDENTITY_DATA_FIX | артикул `AG1210100013` (внутренний код) → `AG 1210-1`, затем поиск фото | DATA → MEDIA | data-fix + 1 поиск |
| 7 | 45441 | Hanskonner HOS8140BL | MEDIA | у ВИ нет; источник вне ВИ (ручная загрузка через `ImagePipeline`) | MEDIA | ручной |
| 8 | 45200 | Einhell TE-AG 125 CE (4430860) | MEDIA | einhell.de `/p/4430860` (карточки есть, CDN-оригинал без `-B200`) | MEDIA | источник известен |
| 9 | 45117 | Einhell TC-BS 8038 (4466260) | MEDIA | einhell.de `/p/4466260` | MEDIA | источник известен |
| 10 | 45142 | Интерскол УПМ-200/1010ЭШ | MEDIA + CHARACTERISTICS, нет артикула | interskol.ru по модели | MEDIA + DATA | identity по модели |
| 11 | 44527 | ЗУБР ЗП-2890 м | MEDIA (VARIANT_IDENTITY_MISMATCH) | у ВИ только «мс»; zubr.ru по «ЗП-2890 м» — не ослабляя identity | MEDIA | ручной |

**Короткая волна** (п. 1–5): 5 SKU, только DATA и TAXONOMY. После нового гейта поднимает выпуск 74 → ~79.
Для п. 5 нужно решение владельца по типу.

## Не входит

- Перетипизация 35 УШМ и 5 полировальных в `bolgarki-ushm` / `polirovalnye`. Это известный gap, а не блокер:
  тип родово верный. Отдельное решение владельца по таксономии.
- Вес (`weight_kg`) у 80 из 85. Пробел качества: не блокирует выпуск (OWNER §11 гейта), а источник даёт
  вес без указания, с АКБ или без (AMBIGUOUS_WEIGHT).
