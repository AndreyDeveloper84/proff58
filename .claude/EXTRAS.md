# Внешние наборы для Claude Code

Здесь описано, какие сторонние коллекции для Claude Code подключены к проекту
«Профессионал», что включено по умолчанию, а что доступно по запросу.

Запрошенные репозитории:

| Репозиторий | Что это | Статус |
|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | Плагин-методология разработки + скиллы | ✅ подключён и **включён** |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | Большой marketplace (67 агентов, 271+ скиллов) | ✅ подключён и **включён** |
| [xu-xiang/everything-claude-code-zh](https://github.com/xu-xiang/everything-claude-code-zh) | Китайский перевод everything-claude-code (подмножество ECC, тот же автор) | ◐ точечный curated-набор (см. раздел 5) |
| [garrytan/gstack](https://github.com/garrytan/gstack) | 23+ скилла «инженерной команды» | 📦 в репозитории, **по запросу** |
| [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | 238 специализированных агентов | 📦 базовый набор включён, остальное **по запросу** |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | Список ссылок (awesome-list) | 🔗 устанавливать нечего, ссылка для справки |

> Установлено «без дублей»: из пары ECC / everything-claude-code взят только ECC
> (он суперсет). Тяжёлые наборы (gstack, все 238 агентов) вынесены в «библиотеку»,
> чтобы не раздувать контекст каждой сессии — включается точечно по необходимости.

---

## 1. Плагины marketplace (superpowers — включён; ecc — через локальные эквиваленты)

> **Важно про remote-окружение.** В облачных сессиях Claude Code сетевой git-прокси
> разрешает только репозиторий проекта — внешние marketplace (`obra/superpowers`,
> `affaan-m/ECC`) при `claude plugin marketplace add` дают **403**. Поэтому наборы
> **вендорятся в репозиторий** и активируются локально, без обращения к github.

**superpowers** — вендорен в [`skills-library/superpowers/`](skills-library/superpowers/)
(скиллы + хуки + `.claude-plugin`). Ставится как плагин из локальной директории:
[`settings.json`](settings.json) объявляет marketplace `superpowers-dev` с
`source: directory` (грузится на старте), а SessionStart-хук
[`hooks/activate-extras.sh`](hooks/activate-extras.sh) переустанавливает его каждую
сессию (эфемерный `~/.claude` обнуляется). Доступны все 14 скиллов: `test-driven-development`,
`systematic-debugging`, `verification-before-completion`, `requesting-code-review`,
`brainstorming`, `writing-plans`, `executing-plans` и др.

**ecc** — целиком не ставится (github заблокирован). Вместо плагина — локальные
эквиваленты из ecc-zh (раздел 5): `django-tdd`, `django-patterns`, `postgres-patterns`
скопированы в активную [`skills/`](skills/) и грузятся как project-скиллы; ревью —
агенты `ecc-{python,database,security}-reviewer`.

Управление:

```bash
claude plugin list                       # что установлено (superpowers)
claude plugin marketplace list           # источники (superpowers-dev → directory)
bash .claude/hooks/activate-extras.sh    # ручная переактивация (обычно делает SessionStart-хук)
```

## 2. Базовый набор агентов (включён)

В [`agents/`](agents/) скопированы 18 агентов из agency-agents, релевантных
backend-проекту на Django/DRF (архитектура, БД, ревью, DevOps/SRE, безопасность,
тестирование API/производительности). Они доступны как сабагенты сразу.

## 3. Библиотеки «по запросу»

### agency-agents — все 238 агентов

Полный набор лежит в [`agent-library/agency-agents/`](agent-library/agency-agents/)
по категориям (engineering, design, marketing, sales, product, security, testing,
finance, gis и т.д.). Чтобы активировать нужного агента:

```bash
cp .claude/agent-library/agency-agents/<категория>/<агент>.md .claude/agents/
```

### gstack — инженерные скиллы (теперь ВКЛЮЧЁН)

Лежит в [`skills-library/gstack/`](skills-library/gstack/) (без тестов и собранного
`diagram-render`). Требуется Bun (для browser/QA-скиллов). **Активируется автоматически**
SessionStart-хуком [`hooks/activate-extras.sh`](hooks/activate-extras.sh): он симлинкует
все 52 скилла в `~/.claude/skills/` (пропуская конфликты имён со встроенными скиллами,
например `review`). Появляются команды `/office-hours`, `/ship`, `/qa`, `/spec`,
`/investigate`, `/health`, `/design-review`, `/plan-eng-review`, `/cso` и др. Часть
browser/ios-скиллов требует Bun и/или Chromium — без них они просто не запустятся.
Подробности — `skills-library/gstack/README.md` и `SKILL.md`.

## 4. awesome-claude-code

Это **курируемый список ссылок** (awesome-list), а не устанавливаемый пакет — ставить
нечего. Сам `README.md` репозитория сейчас — заглушка «TODO»; актуальный полный список
(~210 ресурсов: Agent Skills, Workflows, Tooling, Hooks, Slash-Commands, CLAUDE.md Files,
Status Lines и т.д.) лежит в `README_ALTERNATIVES/README_AWESOME.md`. Используйте как
каталог для поиска новых скиллов/команд/агентов:
<https://github.com/hesreallyhim/awesome-claude-code>

---

## 5. everything-claude-code-zh — точечный curated-набор

Репозиторий — китайское подмножество ECC (уже включён плагином), поэтому **целиком
не ставился** (был бы дубль). Взято только то, что либо дополняет, либо адаптировано
под наш стек:

**Скиллы** — `.claude/skills-library/ecc-zh/`: `django-patterns`, `django-security`,
`django-tdd`, `django-verification`, `postgres-patterns`, `python-testing`,
`backend-patterns`, `tdd-workflow`, `verification-loop` (контент на китайском — дубль ECC
по сути). **Включены** (скопированы в активную `skills/`): `django-tdd`, `django-patterns`,
`postgres-patterns` — как замена недоступному ecc-плагину для ядра A1. Остальные — по
запросу (скопировать нужную папку в `.claude/skills/`).

**Агенты-ревьюеры** — `.claude/agents/ecc-{python,database,security}-reviewer.md`.
Python/DB/security-специализация (запускают `ruff`/`mypy`/`black`, проверки SQL-инъекций
и т.п.) — помогают при ревью PR. Дополняют общий `engineering-code-reviewer`.

**Хук автоформата Python (НЕТТО-НОВОЕ, главная ценность)** —
`.claude/hooks/format-python.sh`, подключён в `settings.json` как `PostToolUse`
(`Edit|Write|MultiEdit`). После правки `.py` гоняет `ruff check --fix` + `black` из
`.venv`. **Намеренно НЕ взяты** JS-ориентированные хуки ecc-zh (Biome/Prettier,
TypeScript-typecheck, `console.log`-варнинги, session-state) — они неприменимы к
Django и/или бесполезны в эфемерном окружении. Хук безопасен: всегда `exit 0`, правит
только `.py` внутри проекта.

---

## Важно про эфемерность окружения

Облачное окружение Claude Code временное: всё, что попадает в `~/.claude`,
пропадает после сессии, а внешние marketplace недоступны (403). Поэтому конфиг
плагинов и сами наборы хранятся **в репозитории** (в `.claude/`) и переживают
пересоздание контейнера, а активация автоматизирована SessionStart-хуком
[`hooks/activate-extras.sh`](hooks/activate-extras.sh): он каждую сессию ставит
плагин `superpowers` из вендоренной директории и симлинкует скиллы `gstack` в
`~/.claude/skills/`. project-скиллы (`skills/`: `django-tdd`, `django-patterns`,
`postgres-patterns`, `reliability`, `devops`, `characterize-subgroup`) грузятся
штатно — хук для них не нужен.
