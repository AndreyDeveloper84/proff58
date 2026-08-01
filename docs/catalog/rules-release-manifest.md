# Release manifest контура `tool_type` (Wave 7.1 / H3)

Единый детерминированный артефакт версии контура распознавания: связывает
первичные входы, версии matcher/gate и метрики последнего **пройденного**
independent gate ([rules-gate-h2.md](rules-gate-h2.md)). Файл —
`data/catalog_processing_rules/rules_release_manifest.v1.json`.

## Зачем

Gate 2.0 отвечает на вопрос «текущие артефакты согласованы и точны?». Release
manifest отвечает на вопрос «какая именно версия контура была признана годной и
чем это доказано?» — и позволяет CI поймать дрейф: любое изменение ruleset,
applied corpus, canonical taxonomy manifest, matcher или метрик gate делает
пересчитанный manifest отличным от зафиксированного, и джоба падает.

## Контракт документа

```json
{"canonical": { ... }, "canonical_hash": "<sha256 канонической сериализации canonical>"}
```

- `canonical` — всё, что зависит **только** от входов: `schema_version`,
  `gate_version`, `matcher_version`, секции `inputs` и `gate`;
- `canonical_hash` — sha256 от `json.dumps(canonical, ensure_ascii=False,
  indent=2, sort_keys=True)` + `\n` (та же сериализация, что и запись файла);
- `generated_at` **в файл не пишется** — время прогона относится к
  non-canonical метаданным и выводится командой в stdout. Поэтому два прогона
  на неизменных входах дают побайтово идентичный файл.

### `inputs`

| Блок | Поля |
|---|---|
| `ruleset` | `path`, `ruleset_id`, `version`, `rules`, `ruleset_hash`, `artifact_sha256` |
| `corpus` | `path`, `corpus_id`, `items`, `artifact_sha256` |
| `taxonomy_manifest` | `path`, `manifest_version`, `options`, `taxonomy_identity_hash`, `manifest_semantic_hash`, `artifact_sha256` |
| `gate_sample` | `path`, `rows`, `artifact_sha256` |
| `labels` | `path`, `labels`, `artifact_sha256` |

`path` — POSIX относительно `BASE_DIR` (портабельность Windows ↔ CI).
`artifact_sha256` — sha256 сырых байтов файла; `ruleset_hash`/`*_hash`
таксономии — канонические content-хэши (не байтовые), как в H1/H2.

### `gate`

`gate_passed` (всегда `true` — иначе manifest не выпускается),
`legacy_taxonomy_hash_allowed`, `metrics` (rows, correct, decisions, precision
без округления, Wilson 95%), `thresholds`, `declared_mismatches`, `warnings`,
`report_schema_version`.

## Инварианты

- Manifest выпускается **только** поверх пройденного gate: если gate вернул
  1 или 2, команда завершается тем же кодом и файл не трогается.
- Всё содержимое `canonical` — пересчитанное (H2 declared-artifact policy);
  самодекларированные поля артефактов не переносятся, а только фиксируются в
  `declared_mismatches` как объект сравнения.
- Байт-стабильность: одинаковые входы → одинаковый файл. Отсутствие
  `generated_at` в файле — часть контракта, а не деталь реализации.
- Команда не пишет в БД, не применяет predictions и не меняет входы.

## Команда

```bash
# генерация/обновление (по умолчанию — default ruleset + frozen 7D sample)
python manage.py catalog_rules_release_manifest

# проверка зафиксированной версии (режим CI)
python manage.py catalog_rules_release_manifest --check
```

С H4 замороженный 7D sample несёт **canonical** `taxonomy_hash`
(`8eba9631…`; TT-NEW-TYPES-BATCH-2 2026-08-01 перевыпустил binding с `ea65486c…`
при добавлении пакета из 10 типов — `shtifty`, `nabory-uplotnitelnyh-kolets`,
`nagruzochnye-vilki`, `krepleniya-ognetushiteley`, `kompressometry`,
`zap-tarelki-opornye`, `prosekateli-profiley-gkl`, `shilya`, `izm-shchupy`,
`siz-kremy-zashchitnye` (`voronki` не создан — дубликат `hoz-voronki` из TT-14);
до этого TT-NEW-TYPES-BATCH 2026-08-01 перевыпускал с `7ac7a9a2…` при
добавлении пакета из 9 типов Ступени 5 — `trubogiby`, `machete-i-sekachi`,
`nabory-klyuchey-imbusovyh`, `kleshchi-prosechnye`, `nozhi-gazonokosilok`,
`stanki-derevoobrabatyvayushchie`, `apparaty-svarki-plastikovyh-trub`,
`osnastka-stroitelnogo-oborudovaniya`, `aksessuary-sharnirno-gubcevogo-instrumenta`;
до этого TT-14 2026-07-31 перевыпускал с `887eea5d…` при
добавлении пакета из 2 типов — `bp-golovki-trimmernye`, `hoz-voronki`;
до этого TT-07 2026-07-28 перевыпускал с `524d4e31…` при добавлении пакета
из 5 типов — `bp-leska`, `gaikoverty`, `gaikoverty-ruchnye`,
`svar-katody`, `zap-boyki`; до этого TT-01 перевыпускал с `fc13be78…` при
добавлении `izm-areometry`), поэтому `--allow-legacy-taxonomy-hash` в штатном
контуре не
нужен: `legacy_taxonomy_hash_allowed` в манифесте = `null`,
`declared_mismatches` = `[]`. Флаг остаётся только для replay исторических
артефактов с legacy DB-order binding.

Флаги: `--manifest` (файл release manifest — цель записи или источник
`--check`), `--check`, `--force`, `--format text|json`, а также переопределение
входов gate: `--ruleset`, `--corpus`, `--taxonomy-manifest`, `--gate-sample`,
`--labels`, `--allow-legacy-taxonomy-hash`.

Запись идемпотентна: байт-идентичный файл → `unchanged`, отличающийся →
требуется `--force`.

## Exit codes

| Код | Значение |
|---|---|
| 0 | manifest выпущен / `--check` совпал |
| 1 | gate thresholds не пройдены (manifest не выпускается) |
| 2 | invalid inputs, blocking gate errors, битый `canonical_hash` или расхождение с зафиксированным manifest |
| 3 | internal error |

## CI

Джоба `catalog-rules-gate` в `.github/workflows/tests.yml` (вызывается из
`ci.yml` на PR и из `deploy.yml` перед деплоем) выполняет два шага:

1. `catalog_rules_gate_validate` на замороженном 7D sample
   (`apps/catalog/tests/fixtures/phase7d-gate-sample-official.json` +
   `phase7d-labels.json`) против **default** ruleset;
2. `catalog_rules_release_manifest --check`.

Exit code команды = статус джобы. Сервисы (Postgres/Redis) не поднимаются:
контур DB-independent. Поблажек нет: с H4 оба шага выполняются **без**
`--allow-legacy-taxonomy-hash`, джоба проходит только на canonical taxonomy
identity — зелёный CI является полным доказательством.

## Обновление manifest

Файл — фиксация того, что уже прошло gate, поэтому обновляется **вместе** с
изменением входов, в том же коммите:

1. изменить ruleset / corpus / манифест таксономии по своей процедуре;
2. прогнать gate вручную и убедиться, что он проходит;
3. `catalog_rules_release_manifest --force` — перегенерировать файл;
4. закоммитить артефакт вместе с изменением; CI (`--check`) подтвердит
   согласованность.

Расхождение в CI без обновления файла — не «шум», а сигнал: контур изменился
без ревью версии.
