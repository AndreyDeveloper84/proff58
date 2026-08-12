# Corpus Summary — applied tool_type corpus v1 (staging, 2026-07-21)

> Артефакт: `scratchpad/phase7a/applied_corpus_tool_type.v1.json` (файл прогона
> run2; содержимое байт-в-байт идентично run1 вне volatile-строки
> `extracted_at`). Статус: draft для Stage 7 ревью. Не repo fixture.
> Шаблон полей — план Task 7 §6.3; review flags — §8.
> v2 (2026-07-21): учтены решения Stage 7 review — правило
> `tt-yashchiki-sumki-*` сужено (32/54), разведены два corpus hash,
> добавлена DEVIATION-2.

```
Corpus Summary
Всего товаров: 54
Всего product_id: 54
Source groups: 19 (распределение ниже)
Catalog categories: 31 (распределение ниже)
Tool types: 32 (распределение ниже)
Unknown: 0 (exclusions: 0; доля 0.0%)
Duplicate product_id: 0
Facts hash (aggregate, Merkle-like: canonical_hash отсортированного
  списка per-item facts_hash; алгоритм зафиксирован планом §6.3):
  90237a615661cacd41caf7f2d520d223532a8bd49c908c74a5256bc79b0d9cc6
Corpus hash: artifact_content_hash =
  81c15c5fbcb94c61c0ec2ff9dce7c14d42f5325c9068756c6e32bef69e37361d
  (canonical_hash(doc БЕЗ extracted_at), источник corpus_id, стабилен);
  отличен от loader_corpus_hash =
  58566aef964b846d36fa644da7791c8a4fe0db79a9912dcdcaf0927191f752ce
  (replay: canonical_hash(полный dict ВКЛЮЧАЯ extracted_at), volatile) —
  разведение имён и алгоритмов: extraction_report.hash_registry
sha256 файла: d5c0117e737db4b31149c237b60aebc7f02dbb0249da71e42089fb16703b0311
Corpus ID: staging-tool-type-6ebb8ac9d856 (content-addressed, data_version)
Rules generated: candidate 11 + shadow_regression 0
Coverage: replay recall 0.5926 (32/54), candidate tier; per-rule hits — ниже
Potential collisions: rule-коллизии на corpus = 0; historical label collisions = 2
Taxonomy gaps: labels вне allowed options = 0; validate_against_taxonomy = [];
  DEVIATION-2: duplicate slug 'steplery' (328 строк / 327 уникальных slug)
Top ambiguous groups: 2 группы (4 строки) — таблица ниже
Performance: extraction 6с/6с / validation 3с / replay 0.047с /
  derivation ~1.5ч / corpus 38160 bytes / peak RAM 227.2 MiB (docker stats)
```

## Source groups (19)

| source_group | count | share |
|---|---:|---:|
| Оснастка | 6 | 11.1% |
| Слесарно-столярный инструмент | 6 | 11.1% |
| Средства индивидуальной защиты | 6 | 11.1% |
| Пневмоинструмент | 5 | 9.3% |
| Измерительный инструмент | 3 | 5.6% |
| Ключи, головки, воротки, удлинители | 3 | 5.6% |
| Наборы инструмента | 3 | 5.6% |
| Сварочное оборудование | 3 | 5.6% |
| Строительно-отделочный инструмент | 3 | 5.6% |
| Автомобильный инструмент | 2 | 3.7% |
| Аккумуляторы и зарядные устройства | 2 | 3.7% |
| Бензоинструмент и расходники для них | 2 | 3.7% |
| Запасные части | 2 | 3.7% |
| Прочее | 2 | 3.7% |
| Хозтовары, сад, огород | 2 | 3.7% |
| Аккумуляторный инструмент | 1 | 1.9% |
| Герметики, пены, клеи и пр отделочные материалы | 1 | 1.9% |
| Мойки | 1 | 1.9% |
| Строительное оборудование | 1 | 1.9% |

## Catalog categories (31)

| category | count | share |
|---|---:|---:|
| 386 Кабель и провод | 5 | 9.3% |
| 364 Гвозди | 4 | 7.4% |
| 380 Весы и счётчики | 4 | 7.4% |
| 367 Кольца и шплинты | 3 | 5.6% |
| 388 Автоматы, УЗО и щиты | 3 | 5.6% |
| 5 Аккумуляторы и зарядные устройства | 2 | 3.7% |
| 27 Измерительный инструмент | 2 | 3.7% |
| 45 Наборы инструмента | 2 | 3.7% |
| 58 Слесарно-столярный инструмент | 2 | 3.7% |
| 197 Малярный инструмент | 2 | 3.7% |
| 216 Органайзеры и кейсы | 2 | 3.7% |
| 330 Редукторы и регуляторы газа | 2 | 3.7% |
| 332 Газосварочное оборудование | 2 | 3.7% |
| 393 Аккумуляторы | 2 | 3.7% |
| 3 Электроинструмент | 1 | 1.9% |
| 35 Хозтовары, сад, огород | 1 | 1.9% |
| 89 Полотна ножовочные | 1 | 1.9% |
| 100 Пики, долота и зубила | 1 | 1.9% |
| 107 Лезвия и ножи сменные | 1 | 1.9% |
| 159 Мойки высокого давления | 1 | 1.9% |
| 161 Насосы | 1 | 1.9% |
| 171 Тросы, стяжки и стропы | 1 | 1.9% |
| 182 Бензопилы | 1 | 1.9% |
| 190 На модерацию | 1 | 1.9% |
| 193 Герметики и монтажные пены | 1 | 1.9% |
| 359 Гайки | 1 | 1.9% |
| 360 Шайбы | 1 | 1.9% |
| 370 Рулетки | 1 | 1.9% |
| 398 Подшипники и сальники | 1 | 1.9% |
| 405 Прочая оснастка | 1 | 1.9% |
| 409 Прочий бензоинструмент | 1 | 1.9% |

Замечание: товар 39427 (label `hoz-lopaty`) находится в служебной
категории «190 На модерацию» — это catalog-размещение вне scope tool_type,
фиксируется как data-quality наблюдение, не как дефект corpus.

## Tool types (32)

| tool_type slug | count | share |
|---|---:|---:|
| adaptery | 5 | 9.3% |
| siz-ochki | 5 | 9.3% |
| bp-pnevmosteplery | 4 | 7.4% |
| krep-shplinty | 3 | 5.6% |
| puskovye-provoda | 3 | 5.6% |
| yashchiki-sumki | 3 | 5.6% |
| dinamometricheskie-klyuchi | 2 | 3.7% |
| hoz-lenty | 2 | 3.7% |
| izm-shtativy | 2 | 3.7% |
| nabory-instrumenta | 2 | 3.7% |
| svar-reduktory | 2 | 3.7% |
| 21 slug по 1 товару (bp-osnastka-pnevmomolotkov, fonari, hoz-lezviya, hoz-lopaty, hoz-setki, krep-shaiby, krep-takelazh, obor-pena, obor-shlangi, otvertki, pilki-polotna, plitkorezy, spetsialnye-klyuchi, strubtsiny, sumki-poyasnye, svar-klemmy, trosorezy-kabelerezy, zap-filtry, zap-shpindeli-valy, zap-svechi, zubila) | 21 | 38.9% |

Источники label: web 52 (96.3%), manual 2 (3.7%). Confidence:
80×2, 85×9, 88×2, 90×12, 92×10, 93×1, 94×4, 95×10, 97×2, 100×2.

## Per-rule hits (candidate tier, replay на corpus)

| rule_ref | slug | hits (product IDs) |
|---|---|---|
| tt-krep-shplinty-nabor | krep-shplinty | 26863, 26864, 26865 |
| tt-puskovye-provoda-startovye | puskovye-provoda | 27250, 27251, 27254 |
| tt-bp-pnevmosteplery-gvozde | bp-pnevmosteplery | 28891, 28892, 28893, 28901 |
| tt-siz-ochki-zashchitnye | siz-ochki | 36300, 36302, 36304, 36377, 36378 |
| tt-dinamometricheskie-klyuchi-klyuch | dinamometricheskie-klyuchi | 12957, 12959 |
| tt-adaptery-universal | adaptery | 1110, 1111, 6681, 6682, 10537 |
| tt-izm-shtativy-derzhatel | izm-shtativy | 10631, 10632 |
| tt-svar-reduktory-regulyator | svar-reduktory | 31106, 31109 |
| tt-hoz-lenty-malyarnaya | hoz-lenty | 37269, 37270 |
| tt-nabory-instrumenta-dielektr | nabory-instrumenta | 22650, 22651 |
| tt-yashchiki-sumki-keys-prochee | yashchiki-sumki | 30223, 30225 |

Для каждого правила hits == derived_from (ни одного лишнего срабатывания
внутри corpus, ни одного пропуска своего товара). Товар 1855
(«Сумка для бензопилы») после Stage 7 review не покрыт правилом
(отклонённая cross-комбинация) — no_match.

## Top ambiguous groups (brand | source_group | category | label | count | product IDs)

| brand | source_group | category | label | count | product IDs |
|---|---|---|---|---:|---|
| (пусто) | Ключи, головки, воротки, удлинители | 380 Весы и счётчики | dinamometricheskie-klyuchi | 2 | 12957, 12959 |
| (пусто) | Ключи, головки, воротки, удлинители | 380 Весы и счётчики | otvertki | 1 | 13936 |
| (пусто) | Слесарно-столярный инструмент | 58 Слесарно-столярный инструмент | strubtsiny | 1 | 32027 |
| (пусто) | Слесарно-столярный инструмент | 58 Слесарно-столярный инструмент | zubila | 1 | 32022 |

Первая группа — известный кейс ADR-0011 (динамометрические ключи vs
отвёртка в одной категории «Весы и счётчики»); закрывается rule
`tt-dinamometricheskie-klyuchi-klyuch` + fixture `fix-otvertka-13936`.
Вторая — два разных label синглтонов в одной source_group+category;
правил не порождает (оба синглтоны).

## Review flags (план §8)

1. **Дисбаланс tool_type** — максимальная доля slug: 9.3% (adaptery,
   siz-ochki); флага > 30% нет. 21 slug (38.9% corpus) представлены 1
   товаром — флагируется как «длинный хвост синглтонов»: ожидаемо для
   research-разметки малыми batch, структурно ограничивает candidate
   recall (см. флаг 6 и F11).
2. **Unknown** — exclusions = 0 (0.0%); разбора не требуется.
3. **Неоднозначность** — ambiguous-групп 2 (4 строки выше); максимальный
   размер группы 2 товара с разными labels; флага «≥ 5 товаров с разными
   labels при похожих facts» нет.
4. **Слишком узкие правила** — правил с ровно 2 product ID в
   derived_from: 6 из 11 (55%): tt-dinamometricheskie-klyuchi-klyuch,
   tt-izm-shtativy-derzhatel, tt-svar-reduktory-regulyator,
   tt-hoz-lenty-malyarnaya, tt-nabory-instrumenta-dielektr,
   tt-yashchiki-sumki-keys-prochee. Помечены `narrow` в derivation doc.
5. **Leakage** — автопроверка `derived_from ⊆ corpus IDs` пройдена
   (derive_result.json). Replay recall НЕ доказывает precision; gate 6.1 —
   только на независимой выборке ≥ 100 predictions (Phase 7B).
6. **Покрытие** — recall 0.5926 ≠ 1.0, разбор overfitting не требуется.
   measured 0.5926 < 0.90 → **F11: ACCEPTED under option (a)** (Stage 7,
   2026-07-21): потолок структурный — 21/54 синглтонов × P0.2 + 1 товар
   (1855), сознательно оставленный без правила после отклонения
   cross-product обобщения; все непокрытые — no_match; wrong-slug = 0;
   rule-коллизии = 0. Ruleset сознательно не выводит там, где нет ≥ 2
   подтверждённых примеров.
7. **facts_hash vs статистика** — `load_corpus` пересчитал все 54
   facts_hash без ошибок (F8 gate пройден); расхождений нет.
8. **Стабильность corpus_hash** — два прогона: artifact_content_hash и
   corpus_id идентичны; файлы различаются ровно одной строкой
   `extracted_at` (byte-diff вне неё = 0) — F9 закрыт.
