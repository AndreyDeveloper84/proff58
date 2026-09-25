# Профессионал — интернет-магазин (B2B + B2C)

Кастомная e-commerce-платформа на Django с интеграцией 1С 7.7 и доставкой по Пензе и области.

Принцип разработки — **catalog-first**: данные каталога (дерево категорий, схема характеристик EAV)
являются критическим путём. 1С — источник истины по цене, остатку и коду номенклатуры;
сайт — мастер по контенту (витринные названия, категории, характеристики, фото, описания).
Связь между системами — по коду/артикулу.

## Стек

- **Backend:** Django 5 + Django REST Framework
- **БД:** PostgreSQL
- **Очереди/кэш:** Redis + Celery (worker + beat)
- **Контейнеризация:** Docker / docker-compose
- **Качество кода:** ruff + black + pre-commit, CI на GitHub Actions

## Структура репозитория

```
config/            # Django-проект: настройки (base/dev/prod), urls, celery
apps/
  accounts/        # кастомный User (вход по телефону/e-mail), профиль, роли B2C/B2B
requirements/      # base / dev / prod зависимости
.github/           # CI, шаблоны PR и issue
docker-compose.yml # web, db, redis, celery, celery-beat
```

## Быстрый старт (локально, Docker)

```bash
cp .env.example .env
docker compose up --build
# применить миграции и создать суперпользователя
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Сайт: http://localhost:8000 · Админка: http://localhost:8000/admin/

## Быстрый старт (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Тесты локально

Тестам нужен PostgreSQL (используются JSONB-фасеты, GIN — SQLite не подойдёт). По
умолчанию подключение идёт на `localhost:5432` (см. `DATABASE_URL`).

```bash
docker compose up -d db          # поднять только Postgres (проброшен на localhost:5432)
pytest                           # из venv, без Docker для самих тестов
```

Альтернатива — гонять тесты внутри контейнера: `docker compose run --rm web pytest`
(там `DATABASE_URL` указывает на сервис `db`). В CI хост задаётся явно.

## Ветки и поток работы

- `main` — продакшн, защищённая ветка, всегда деплоится.
- `dev` — интеграционная ветка, в неё вливается вся работа.
- Рабочие ветки от `dev`: `feature/<area>-<кратко>`, `fix/<...>`, `chore/<...>`, `design/<...>`.
- Поток: ветка → PR в `dev` (1 ревью + зелёный CI) → по завершении вехи релизный PR `dev → main` с тегом `vX.Y`.
- Коммиты — [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`).

## Дорожная карта

Вехи M0–M6 и распределение по дорожкам (Дизайн / Данные+интеграции / Приложение+витрина)
описаны в issue-эпиках репозитория и в дорожной карте проекта.

## Архитектура

Целевые границы модулей, сервисные контракты, сигналы и правила отделения движка
от конкретного магазина описаны в [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
