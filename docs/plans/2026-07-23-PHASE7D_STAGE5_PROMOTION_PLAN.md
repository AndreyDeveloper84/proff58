# Phase 7D Stage 5 — Promotion tool_type.v2 → default RULESET_PATH (план)

**Статус:** v2, 2026-07-23. D-5.1–D-5.4 решены пользователем (§6); добавлено F-5.6. **AUTHORIZED: Stage 5.0 + Stage A** — mandatory STOP после A; Stage B (commit), Stage C (push/CI deploy), rollback, cleanup, production, изменения JSON НЕ авторизованы. Основан на Stage 4 verdict **PROMOTE**
(Decision owner: Product Owner, 2026-07-23; протокол
`scratchpad/phase7d/phase7d-report.md`). Выполняется только после отдельной
авторизации пользователя, по стадиям, с обязательными STOP между
authorization boundaries.

## 1. Цель и граница

Переключить default ruleset контура rules shadow/gate с `tool_type.v1.json`
на `tool_type.v2.json` минимальным изменением, без изменения самих JSON,
с полным regression-suite, staging smoke против frozen reference и
rollback через revert promotion commit.

**Граница:** promotion меняет только *default* в
`apps/catalog/rules_engine.py:30`. Это НЕ применение predictions к
каталогу, НЕ изменение товаров/БД, НЕ признание статистически доказанной
precision ≥ 0.99 (ограничения Stage 4 сохраняются: Overall Wilson 95% CI
[0.947042, 0.998284]; 5 правил zero-support; малые support — observational;
gate пройден на границе 102/103).

## 2. Pins (freeze-контракт)

| Артефакт | Pinned значение |
|---|---|
| HEAD до изменения | `2375d8e4b542f1acea1e6576df98921f2e8d005e` (commit 7C) |
| Ruleset v2 | LF sha256 `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec`; canonical ruleset_hash `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` |
| Ruleset v1 (остаётся в репо, не меняется) | LF sha256 `b476199afaf83e7f305d335d7ed2c77d855469f59fd73dbfe357c9183d7d1e6e` |
| Applied corpus | LF sha256 `6663a6fe48c2c2656604a179c1f70338a08a9d3e2a364a5ec2f663600b85d6e3` |
| taxonomy_hash | `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` |
| input_universe_hash | `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` |
| Official sample (frozen) | byte sha256 `873ee2a19e7dedbc322357f8ff4108690b4e3f6a25889571e13c5f7191bfdeb8` |
| Labels (frozen) | byte sha256 `4cb05d36213d1183c9fe93956471118beb253042b5dd40a3454df9ad143928f1` |
| Reference shadow report (counts/ordered) | 7D official `scratchpad/phase7d/phase7d-shadow-report-v2-official.json` sha256 `a22e1d1ace94f95f2480f68eb4b43f4ae7a355dc984445a6bf3815f6fd12ae9d` (== 7C reference `4c1f39d3…` по counts/ordered/per_rule, сверено Stage 1.3(b)) |

LF-проверка рабочей копии — через `sed 's/\r$//'` (рабочая копия CRLF,
пины — LF, прецедент Stage 0 фаз 7C/7D).

## 3. Факты среды, определяющие план (проверено 2026-07-23)

1. **Blast radius изменения минимален.** `rules_engine` импортируют только
   `catalog_rules_shadow`, `catalog_rules_gate_validate` и тесты.
   Продакшен-код каталога (enrich/import/queue/provenance) `RULESET_PATH`
   не потребляет. Default используется лишь при запуске этих двух команд
   без `--ruleset` (`catalog_rules_shadow.py:226`: `load_ruleset(None)` →
   `RULESET_PATH`).
2. **Тесты от default не зависят.** `test_rules_corpus_replay.py:37`
   пинит собственную константу на v1; `test_rules_engine.py` /
   `test_rules_shadow_command.py` строят inline-ruleset'ы. Изменение
   строки 30 не должно ломать suite; regression-suite это подтверждает.
3. **Test runner — pytest** (`.github/workflows/tests.yml:81`).
4. **Coupling push↔deploy.** Push в `dev` автоматически запускает
   `.github/workflows/deploy.yml`: tests → SSH на VPS →
   `git reset --hard origin/dev` → `docker compose -f
   docker-compose.prod.yml build` → `docker/release.sh` (бэкап БД +
   миграции; новых миграций в этом изменении нет) → `up -d --build` →
   nginx reload → CSP smoke. **«Deploy staging» механически является
   следствием «push to dev» и не может быть выполнен отдельно от push
   в рамках существующего контура.** Это вынесено в D-5.1.
5. Staging v2-файл попадёт на сервер через git (файл закоммичен в 7C),
   путь в контейнере `/app/data/catalog_processing_rules/tool_type.v2.json`.
6. Локальная dev-БД ≠ staging-вселенная: проверки «predictions=325,
   ordered == reference» выполняются **только на staging**; локально
   проверяются ruleset_id/ruleset_hash/default-switch и pytest.

## 4. Scope / Non-scope

**Scope:**

- freeze re-verification (sample, labels, v2, HEAD);
- однострочное изменение `RULESET_PATH` v1 → v2;
- полный regression suite (pytest);
- локальный smoke default-switch;
- отдельный promotion commit (ровно 1 файл);
- push в `dev` → auto-deploy staging → staging shadow smoke с default
  ruleset против frozen reference;
- активация post-promotion monitoring (§8);
- протокол в `scratchpad/phase7d/phase7d-report.md`.

**Non-scope:**

- изменение любых JSON (v2, v1, corpus); создание v2.1 (D-4 фазы 7D по
  решению Stage 4 не применяется);
- применение predictions к каталогу; любые записи в БД;
- изменение matcher/taxonomy/схем/команд;
- PR, push в `main`, production deploy;
- включение чужих pre-existing изменений (`M
  docs/catalog/stroitelnyy-roadmap.md` и прочий untracked-мусор) в
  promotion commit.

## 5. Разрешённые операции / запреты

Разрешено (по стадиям §7, каждая — по своей авторизации): редактирование
`apps/catalog/rules_engine.py` (одна строка); локальный `pytest`; локальный
`catalog_rules_shadow` (read-only по построению); `git add`/`git commit`
(Stage B); `git push origin dev` (Stage C); SSH read-only smoke на staging;
запись артефактов только в `scratchpad/phase7d/` (локально) и
`/app/logs/phase7d-stage5-*` (staging).

Запрещено: push до авторизации Stage C; любые git mutations вне Stage B/C;
push в `main`; force-push; изменение JSON ruleset/corpus; записи в БД;
изменения файлов вне перечисленных; удаление 7D-артефактов до D-5.3.

## 6. D-решения (требуют подтверждения при авторизации)

- **D-5.1 (push↔deploy coupling).** **РЕШЕНИЕ (2026-07-23): ПРИНЯТО.**
  push → GitHub Actions → deploy.yml → staging deploy — единая атомарная
  операция. Авторизация Stage C автоматически включает staging deploy,
  инициированный CI; deploy не становится самостоятельным ручным
  действием. Границы сохраняются: Stage B (commit) → STOP → Stage C
  (push → CI deploy → staging smoke) → STOP.
- **D-5.2 (cadence drift-контроля).** **РЕШЕНИЕ (2026-07-23): ПРИНЯТО.**
  Read-only shadow replay на staging на +7 и +30 дней после promotion
  (counts / ordered predictions / per-rule counters против frozen
  reference). Это read-only verification, не новый аудит качества; любые
  отличия — событие мониторинга, а не автоматический rollback. Механизм
  (cron-сессии/ручной запуск) авторизуется отдельно.
- **D-5.3 (cleanup 7D).** **РЕШЕНИЕ (2026-07-23): ПРИНЯТО С УТОЧНЕНИЕМ.**
  Удаление только после того, как: все SHA зафиксированы, финальный отчёт
  принят, promotion успешно завершён. `phase7d-report.md` и финальные
  freeze-артефакты НЕ удаляются. Удаляемое: временные генераторы
  (`analyze_stage1.py`, `build_prelim_labels.py`, `gen_review_doc.py`,
  `build_final_labels.py`, `stats_stage3.py`, `tool_type.v2.lf.json`),
  промежуточные replay (`*-replay.json`), контейнерные
  `/app/logs/phase7d-*` (8 файлов).
- **D-5.4 (аварийный rollback).** **РЕШЕНИЕ (2026-07-23): ПРИНЯТО
  (усилено).** При F-5.4 (staging smoke mismatch: ordered diff не пуст /
  ruleset_hash другой / predictions ≠ 325 / collisions ≠ 0)
  `git revert <promotion-commit>` + push выполняются **немедленно**, без
  ожидания дополнительного approval: rollback восстанавливает уже
  подтверждённое состояние. Разбор причин — после rollback.

## 7. Стадии и authorization boundaries

### Stage 5.0 — Freeze re-verification (внутри авторизации A, до правки)

- [ ] HEAD == `2375d8e4b542f1acea1e6576df98921f2e8d005e` (`git log -1`);
  `git status --short` — нет новых tracked-модификаций (чужая
  pre-existing `M docs/catalog/stroitelnyy-roadmap.md` фиксируется и в
  commit не входит).
- [ ] v2 LF sha256 == `ff449701…`; canonical ruleset_hash ==
  `9bf0271a…` (`load_ruleset`); v1/corpus LF == pins; sample ==
  `873ee2a1…`; labels == `4cb05d36…`.
- [ ] Любое расхождение → F-5.1, правка не выполняется.

### Stage A — локальное изменение + regression (авторизация A)

- [ ] **A.1** Edit `apps/catalog/rules_engine.py:30`:
  `… / "tool_type.v1.json"` → `… / "tool_type.v2.json"`. Ровно одна
  строка; JSON не трогаем.
- [ ] **A.2** `pytest` — полный suite, 0 failures. Провал → F-5.2 +
  немедленный локальный откат (`git checkout -- apps/catalog/rules_engine.py`).
- [ ] **A.3** Локальный smoke default-switch (без `--ruleset`):

```bash
PYTHONPATH=. PYTHONIOENCODING=utf-8 DJANGO_SETTINGS_MODULE=config.settings.dev \
  ./.venv/Scripts/python.exe manage.py catalog_rules_shadow \
  --pool all --out scratchpad/phase7d/phase7d-stage5-local-default-smoke.json
```

  Ожидания: exit 0; `ruleset_id=tool_type.v2`; `ruleset_hash=9bf0271a…`.
  Counts/predictions локально — только информационно (dev-БД ≠ staging).
- [ ] **A.4** Diff review: `git diff --stat -- apps/catalog/rules_engine.py`
  = `1 file changed, 1 insertion(+), 1 deletion(-)`; полный `git diff` —
  одна строка; единственная иная tracked-модификация в дереве — чужая
  pre-existing `M docs/catalog/stroitelnyy-roadmap.md` (не трогаем).
- [ ] **STOP A** → пользователю: pytest-вывод, smoke evidence, diff.

### Stage B — promotion commit (авторизация B)

- [ ] **B.0 (F-5.6)** Pre-commit guard: после `git add` —
  `git diff --cached --stat` = ровно `1 file changed, 1 insertion(+),
  1 deletion(-)`; посторонний файл или EOL/formatter churn → STOP.
- [ ] **B.1** `git add apps/catalog/rules_engine.py` (только этот файл).
- [ ] **B.2** Commit, сообщение:
  `feat(catalog): promote tool_type.v2 to default ruleset (Phase 7D Stage 5)`
- [ ] **B.3** Scope check: `git show --stat HEAD` — ровно 1 файл, 1
  добавление/1 удаление. Иначе → F-5.3 (откат локального commit'а).
- [ ] **STOP B** → пользователю: sha commit'а, stat, полный diff.
  Push по-прежнему не авторизован.

### Stage C — push → auto-deploy staging → smoke (авторизация C, включает D-5.1)

- [ ] **C.1** `git push origin dev`. CI: tests (deploy.yml → tests.yml)
  должны быть зелёными; задеплоенный run зафиксировать (`gh run list` /
  вывод Actions).
- [ ] **C.2** Post-deploy staging smoke **с default ruleset** (без
  `--ruleset` — это и есть проверка promotion):

```bash
ssh -o BatchMode=yes taximeter@194.87.99.126 \
  docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --pool all --out /app/logs/phase7d-stage5-smoke-default.json
```

  Ожидания: exit 0; `ruleset_hash=9bf0271a…`; `predictions=325`;
  `collisions=0`; `rewrite_attempts=0`;
  `input_universe_hash=82536a46…`; `taxonomy_hash=b357be60…`;
  pool=1593 / typed_excluded=18123.
- [ ] **C.3** Ordered-сверка: скопировать report локально
  (`docker cp` → `scratchpad/phase7d/phase7d-stage5-smoke-default.json`),
  normalized diff против frozen reference `a22e1d1a…` (volatile
  keys/out-пути исключаются): упорядоченный список
  `product_id → option_slug` (n=325) идентичен; `per_rule` counters
  идентичны. Расхождение → F-5.4 → rollback по D-5.4.
- [ ] **STOP C** → пользователю: CI-статус, полные counters, hashes,
  результат diff, подтверждение zero-write.

### Stage D — monitoring activation + финальный протокол (внутри C или отдельно)

- [ ] **D.1** Зафиксировать в `phase7d-report.md` секцию Stage 5:
  verdict, commit sha, push, deploy evidence, smoke evidence, monitoring
  plan (§8), cleanup по D-5.3 (с sha256 удаляемого).
- [ ] **D.2** Зарегистрировать monitoring cases (§8) в протоколе.
- [ ] **STOP D** → финальный отчёт фазы 7D целиком.

## 8. Post-promotion monitoring (обязательный, из требований Stage 4)

- **M-1 (product_id=31104, правило `tt-svar-reduktory-regulyator`).**
  Статус: unverifiable (Stage 2.2). Без автоматического изменения
  результата. Триггеры пересмотра: (а) изменение facts товара
  (name/article/PAV); (б) следующий precision audit. Если новые
  разрешённые источники покажут incorrect — отдельный exception-процесс
  (v2.1 по D-4 плана 7D) с новой авторизацией; молча не исправляется.
- **M-2 (пять zero-support rules).** `tt-bp-trimmery-akkum`,
  `tt-izm-ruletki-mernaya-lenta`, `tt-krep-shplinty-nabor`,
  `tt-nabory-instrumenta-dielektr`, `tt-sumki-poyasnye-podsumok`.
  Precision не измерена (нет строк в sample). Их predictions из
  universe-325 подлежат **принудительному включению** (D-1-style
  amendment) в следующий human-labeled audit; до этого они считаются
  unmeasured, а не подтверждёнными.
- **M-3 (drift-контроль, D-5.2).** Контрольные read-only replay на
  staging (+7д, +30д): counts/ordered/per_rule против frozen reference.
  Drift → доклад пользователю; решение о rollback — только пользователь.
- **M-4 (граница gate).** Promotion принят на границе (102/103; ещё одна
  non-correct — и gate был бы провален). Любой будущий audit v2 — не
  менее 100 строк с принудительным monitoring-представительством.

## 9. Rollback

- **До commit'а:** `git checkout -- apps/catalog/rules_engine.py`.
- **После commit'а, до push:** откат локального commit'а (не pushed);
  рабочее дерево возвращается к pinned HEAD.
- **После push (основной механизм):** `git revert <promotion-commit>` →
  push в `dev` → auto-deploy возвращает default на v1. БД-откат не
  требуется: изменение не несёт миграций и записей (release.sh выполнит
  штатный бэкап, миграции — no-op).
- Инвариант: v1-файл остаётся в репо неизменным (pin `b476199a…`),
  поэтому revert полностью восстанавливает поведение pre-promotion.

## 10. F-условия (немедленный STOP)

- **F-5.1.** Freeze-расхождение любого pin §2 или HEAD до правки.
- **F-5.2 (уточнено Product Owner 2026-07-23).** Срабатывает при любом
  НОВОМ failure или изменении failure signature относительно pinned v1
  baseline. Baseline exceptions (waived только для локального Stage A и
  только при идентичном воспроизведении на v1): (1)
  `tests/test_regression_mvp.py::test_healthcheck_returns_ok` — Redis
  недоступен в локальной среде; (2)
  `tests/test_deploy_release.py::test_release_script_is_executable` —
  Windows checkout не материализует POSIX exec bit (git index: 100755;
  авторитетная проверка — Linux CI). Любой дополнительный failure,
  исчезновение/изменение ожидаемого контекста или падение профильного
  catalog-rules контура → STOP + revert. Зелёный CI на Linux перед
  staging deploy остаётся обязательным.
- **F-5.3.** Scope promotion commit'а ≠ ровно `rules_engine.py` (1 строка).
- **F-5.4.** Staging smoke: ruleset_hash/predictions/collisions/universe
  mismatch или ordered diff ≠ empty → rollback по D-5.4.
- **F-5.5.** Любая запись в БД; изменения вне разрешённых путей; drift
  frozen JSON.
- **F-5.6.** Pre-commit: diff ≠ «1 file / 1 insertion / 1 deletion»
  (посторонний файл, EOL/formatter churn) → STOP, commit не выполняется.

## 11. Acceptance criteria

1. Freeze: все pins §2 зелёные до и после правки (кроме самой строки 30).
2. Promotion commit: ровно 1 файл, 1 строка; v2/v1/corpus JSON
   байт-неизменны.
3. Полный pytest зелёный после правки.
4. Staging smoke с default ruleset: `ruleset_hash=9bf0271a…`,
   predictions=325, collisions=0, ordered == frozen reference.
5. Monitoring cases M-1/M-2 и cadence M-3 зафиксированы в протоколе.
6. Rollback-путь (revert) задокументирован и готов; push в `main`,
   production deploy, применение predictions не выполнялись.
