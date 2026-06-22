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

## 1. Плагины marketplace (включены)

Зарегистрированы в [`settings.json`](settings.json) (`extraKnownMarketplaces` +
`enabledPlugins`) и подтянутся автоматически в каждой сессии:

- `superpowers@superpowers-dev`
- `ecc@ecc`

Управление:

```bash
claude plugin list                       # что установлено
claude plugin details ecc                # инвентарь и оценка токенов
claude plugin disable ecc@ecc            # временно отключить
claude plugin marketplace update         # обновить из источников
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

### gstack — инженерные скиллы

Лежит в [`skills-library/gstack/`](skills-library/gstack/) (без тестов и собранного
`diagram-render`, чтобы уменьшить вес). Требуется Bun. Активация — симлинк в
пользовательскую папку скиллов, после чего gstack подхватится как скилл:

```bash
ln -s "$(pwd)/.claude/skills-library/gstack" ~/.claude/skills/gstack
# либо штатный установщик gstack:
( cd .claude/skills-library/gstack && ./setup )
```

После активации появятся команды gstack (`/office-hours`, `/review`, `/ship`,
`/qa`, `/design`, `/cso` и др.). Подробности — в
`skills-library/gstack/README.md` и `skills-library/gstack/SKILL.md`.

## 4. awesome-claude-code

Это курируемый список ссылок, а не устанавливаемый пакет. Используйте его как
каталог для поиска новых скиллов/команд/агентов:
<https://github.com/hesreallyhim/awesome-claude-code>

---

## 5. everything-claude-code-zh — точечный curated-набор

Репозиторий — китайское подмножество ECC (уже включён плагином), поэтому **целиком
не ставился** (был бы дубль). Взято только то, что либо дополняет, либо адаптировано
под наш стек:

**Скиллы (по запросу)** — `.claude/skills-library/ecc-zh/`: `django-patterns`,
`django-security`, `django-tdd`, `django-verification`, `postgres-patterns`,
`python-testing`, `backend-patterns`, `tdd-workflow`, `verification-loop`. Локальный
быстрый доступ к Django/Python-практикам (контент на китайском — дубль ECC по сути).

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
пропадает после сессии. Поэтому конфиг плагинов и сами наборы хранятся **в
репозитории** (в `.claude/`) и переживают пересоздание контейнера. Команды
активации из раздела 3 при необходимости можно вынести в SessionStart-хук.
