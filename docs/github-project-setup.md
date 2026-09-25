# Настройка GitHub Project, доски и branch protection

> **Для кого:** owner репозитория (AndreyDeveloper84).
> Действия ниже требуют прав **Admin** в репозитории `AndreyDeveloper84/proff58`.

---

## 1. GitHub Project v2

### 1.1 Создать проект

1. Перейти на <https://github.com/AndreyDeveloper84/proff58> → **Projects** → **New project**.
2. Выбрать шаблон **Board** (Kanban).
3. Название: **Профессионал — Roadmap** (или аналогичное).

### 1.2 Настроить колонки (поле Status)

Открыть настройки поля **Status** и привести к виду:

| Колонка       | Описание                     |
|---------------|------------------------------|
| Backlog       | Задачи в очереди             |
| Ready         | Готовы к взятию в работу     |
| In Progress   | В работе                     |
| Review        | На ревью / ожидание мёрджа  |
| Done          | Завершено                    |

Удалить или переименовать дефолтные колонки (Todo, In Progress, Done) в соответствии с таблицей.

### 1.3 Добавить кастомные поля

В настройках проекта добавить:

| Поле       | Тип               | Значения                                                    |
|------------|--------------------|-------------------------------------------------------------|
| Priority   | Single select      | P0-critical, P1-high, P2-medium, P3-low                    |
| Size       | Single select      | XS, S, M, L, XL                                            |
| Area       | Single select      | backend, frontend, infra, docs, design                      |
| Iteration  | Iteration          | 2-недельные итерации, начиная с ближайшего понедельника     |

---

## 2. Branch protection rules

Перейти в **Settings → Branches → Add branch ruleset** (или Add classic branch protection rule).

### 2.1 Ветка `main`

| Параметр                                | Значение                       |
|-----------------------------------------|--------------------------------|
| Branch name pattern                     | `main`                         |
| Require a pull request before merging   | Да                             |
| Required approvals                      | **1**                          |
| Require status checks to pass           | Да                             |
| Required status checks                  | `tests / lint`, `tests / test` |
| Require branches to be up to date       | Да                             |
| Do not allow force pushes               | Да                             |
| Do not allow deletions                  | Да                             |

> **Важно:** названия status checks `tests / lint` и `tests / test`
> формируются из reusable workflow `tests.yml`, вызываемого через `ci.yml`.
> После первого прогона CI на PR эти имена станут доступны в автодополнении.

### 2.2 Ветка `dev`

| Параметр                                | Значение                       |
|-----------------------------------------|--------------------------------|
| Branch name pattern                     | `dev`                          |
| Require a pull request before merging   | Да                             |
| Required approvals                      | **0** (или 1 по желанию)      |
| Require status checks to pass           | Да                             |
| Required status checks                  | `tests / lint`, `tests / test` |
| Require branches to be up to date       | Да (рекомендуется)             |
| Do not allow force pushes               | Да                             |

---

## 3. Labels (метки вех M0-M6)

### Проверка существующих labels

```bash
gh label list --repo AndreyDeveloper84/proff58 --limit 50
```

### Необходимые labels

**Вехи:**

| Label | Цвет      | Описание                        |
|-------|-----------|---------------------------------|
| M0    | `#0E8A16` | Веха 0 -- CI/CD, инфраструктура |
| M1    | `#1D76DB` | Веха 1 -- MVP каталог           |
| M2    | `#5319E7` | Веха 2 -- Личный кабинет        |
| M3    | `#D93F0B` | Веха 3 -- Заказы и корзина      |
| M4    | `#F9D0C4` | Веха 4 -- Оплата и доставка     |
| M5    | `#C2E0C6` | Веха 5 -- Аналитика и отчёты    |
| M6    | `#FEF2C0` | Веха 6 -- Полировка и запуск    |

**Типы:**

| Label        | Цвет      | Описание               |
|--------------|-----------|------------------------|
| type:bug     | `#D73A4A` | Баг                    |
| type:feature | `#0075CA` | Новая функциональность |
| type:chore   | `#CFD3D7` | Инфра / обслуживание   |
| type:docs    | `#0075CA` | Документация           |

### Создание недостающих labels через CLI

```bash
# Вехи
gh label create M0 --color 0E8A16 --description "Веха 0 — CI/CD, инфраструктура" --repo AndreyDeveloper84/proff58
gh label create M1 --color 1D76DB --description "Веха 1 — MVP каталог" --repo AndreyDeveloper84/proff58
gh label create M2 --color 5319E7 --description "Веха 2 — Личный кабинет" --repo AndreyDeveloper84/proff58
gh label create M3 --color D93F0B --description "Веха 3 — Заказы и корзина" --repo AndreyDeveloper84/proff58
gh label create M4 --color F9D0C4 --description "Веха 4 — Оплата и доставка" --repo AndreyDeveloper84/proff58
gh label create M5 --color C2E0C6 --description "Веха 5 — Аналитика и отчёты" --repo AndreyDeveloper84/proff58
gh label create M6 --color FEF2C0 --description "Веха 6 — Полировка и запуск" --repo AndreyDeveloper84/proff58

# Типы (если отсутствуют)
gh label create "type:bug" --color D73A4A --description "Баг" --repo AndreyDeveloper84/proff58
gh label create "type:feature" --color 0075CA --description "Новая функциональность" --repo AndreyDeveloper84/proff58
gh label create "type:chore" --color CFD3D7 --description "Инфра / обслуживание" --repo AndreyDeveloper84/proff58
gh label create "type:docs" --color 0075CA --description "Документация" --repo AndreyDeveloper84/proff58
```

---

## 4. Issue и PR templates

Шаблоны уже созданы в репозитории:

| Файл                                    | Назначение            |
|-----------------------------------------|-----------------------|
| `.github/ISSUE_TEMPLATE/bug.md`         | Баг-репорт            |
| `.github/ISSUE_TEMPLATE/task.md`        | Рабочая задача        |
| `.github/ISSUE_TEMPLATE/feature.md`     | Запрос функциональности |
| `.github/ISSUE_TEMPLATE/config.yml`     | Конфигурация шаблонов |
| `.github/PULL_REQUEST_TEMPLATE.md`      | Шаблон PR             |

---

## 5. Чек-лист выполнения

- [ ] GitHub Project v2 создан с колонками Backlog / Ready / In Progress / Review / Done
- [ ] Поля Priority, Size, Area, Iteration добавлены в проект
- [ ] Branch protection для `main` настроен (PR + 1 approval + CI + no force push)
- [ ] Branch protection для `dev` настроен (PR + CI)
- [ ] Labels M0-M6 существуют
- [ ] Labels type:bug, type:feature, type:chore, type:docs существуют
- [ ] Issue/PR templates проверены и отображаются корректно
