# SP2 · Дизайн-система витрины «Профессионал» (#39, #474)

Базовый набор токенов и компонентов, снимающий дизайн-блокер для frontend-разработки
витрины MVP (#6). Живой эталон — страницы `/demo/ui` (kitchen-sink) и `/demo/screens`
(макеты экранов), обе с переключателем светлой/тёмной темы.

## Принцип

Цвета, типографика и радиусы заданы **токенами** в `frontend/app/globals.css`
(CSS-переменные) и замаплены в Tailwind v4 через `@theme inline`. Компоненты
**никогда** не хардкодят цвета — только утилиты токенов (`bg-surface`, `text-ink`,
`border-line`, …). Перекраска экземпляра магазина = смена `--accent` / `--primary`
из `SiteSettings`, без правки компонентов.

## Стратегия темы (SP2.1 #474, утверждено #477)

**Светлая — основная** (утверждённое UX-направление, #477). Дефолтные значения
токенов (`:root` / `[data-theme="light"]`) — светлые, для рабочих e-commerce
поверхностей (каталог, PDP, checkout, ЛК): легче читать каталог, чище фото товара,
лучше считываются цены/статусы. Живой `<html>` без класса — светлый по умолчанию.

**Тёмная — secondary** (`.dark` класс или `[data-theme="dark"]`): доступна как
dark-mode/демо, не ломается. Ближайший предок с темой выигрывает при резолве var,
поэтому светлый каталог и тёмная шапка сосуществуют на одной странице.

**Тёмная брендовая рамка**: шапка и подвал всегда тёмные — через отдельные
тема-независимые токены `--header-…` / `--footer-…` (утилиты `bg-header`,
`text-header-ink`, `border-header-line`, `bg-footer`, …), применённые в макете
шапки `/demo/screens`. Реальные `Header`/`Footer` несут класс `.dark` на корне
(dark-токены в их поддереве) — остаются тёмными на светлом сайте без правки внутренностей.

Компоненты используют **только семантические токены** (никакого raw-hex) →
переключение темы их не трогает. Контраст светлой палитры — AA (body ≥ 4.5:1).
Инстанс-цвета `--primary`/`--accent` из `SiteSettings` (inline на `<html>`) должны
выбираться контрастными на белом.

## Токены

### Поверхности и текст (тёмная тема)
| Токен | Утилита | Назначение |
|---|---|---|
| `--bg` | `bg-canvas` | фон страницы |
| `--surface` | `bg-surface` | карточки, поля |
| `--surface-raised` | `bg-raised` | приподнятые блоки, hover |
| `--border` | `border-line` | границы |
| `--text` | `text-ink` | основной текст |
| `--text-secondary` | `text-ink-2` | вторичный текст, лейблы |
| `--text-muted` | `text-ink-3` | подписи, placeholder |

### Бренд и семантика
| Токен | Утилита | Назначение |
|---|---|---|
| `--accent` | `bg-accent` / `text-accent` | CTA, активные состояния |
| `--accent-ink` | `text-accent-ink` | текст на accent |
| `--primary` | `bg-brand` / `text-brand` | ссылки, «в наличии», success |
| `--danger` | `bg-danger` / `text-danger` | скидка, ошибка, «нет в наличии» |
| `--rating` | `text-rating` | звёзды рейтинга |

Статусы заказа: `--st-wait|confirm|assemble|ship|done|cancel` → `bg-st-*`.

### Типографика
- `font-sans` (`--font-inter`) — основной текст.
- `font-display` (`--font-oswald`) — заголовки.

### Радиусы
`rounded-sm` (6px) · `rounded-md` (10px) · `rounded-lg` (12px) · `rounded-full` (pill).

### Фокус и доступность
Глобальный `:focus-visible` — обводка `--accent`. Спиннеры уважают
`prefers-reduced-motion`. Поля с ошибкой ставят `aria-invalid`; `Field` связывает
label ↔ контрол по `id`.

## Компоненты (`frontend/components/ui/`)

| Компонент | Назначение | Ключевые пропсы |
|---|---|---|
| `Button` | действия | `variant` = accent/outline/ghost, `size` |
| `Badge` | метки | `variant` = hit/sale/new/neutral |
| `Card` | контейнер-поверхность | `surface` = base/raised, `pad` |
| `Input` | текстовое поле | `invalid` |
| `Textarea` | многострочное поле | `invalid` |
| `Field` | label + контрол + ошибка/подсказка | `label`, `error`, `hint`, `required` |
| `Spinner` | индикатор загрузки | `size`; цвет = `currentColor` |
| `EmptyState` | пусто (нет результатов/корзина пуста) | `title`, `description`, `action` |
| `ErrorState` | ошибка загрузки/действия | `title?`, `description?`, `action` |
| `LoadingState` | загрузка экрана/блока | `label` |
| `SuccessState` | успех (заказ оформлен) | `title`, `description`, `action` |

Скелетоны списков — `components/listing/ProductGridSkeleton`.

## Покрытие MVP (#6)
- **Каталог / PLP**: Card, Badge, Button, EmptyState (нет товаров), LoadingState, скелетоны.
- **Карточка товара**: Card, Badge, Button, состояния наличия.
- **Checkout**: Field + Input/Textarea (контакты/реквизиты), Card (сводка заказа),
  SuccessState (заказ оформлен), ErrorState (сбой оплаты/оформления).

Все базовые дизайн-решения зафиксированы — frontend собирает #6 без новых базовых
дизайн-развилок.

## A11y и touch-target (SP2.1)

- **`Field`** сам связывает label ↔ контрол (`htmlFor`/`id`), пробрасывает контролу
  `aria-describedby` (на error/hint), `aria-invalid` (на error) и `required` через
  props-bag render-prop; покрыт тестами (`components/ui/field.test.tsx`).
- **`Input`/`Textarea`** подсвечивают ошибку через стандартный `aria-invalid`
  (вариант `aria-invalid:border-danger`) — один источник правды для стиля и a11y.
- **Touch-target**: `Button` и `Input` на мобиле ≥ 44px (`h-11 sm:h-9`).
- Глобальный `:focus-visible` (обводка accent) и `role="status"` у Spinner/LoadingState.

## QA (SP2.1, #474)

Автоматически (docker `node:20`): `eslint`, `tsc --noEmit`, `vitest` (12 тестов),
`next build` — зелёные. `/demo/ui` и `/demo/screens` собираются статикой, обе темы.

Структурно проверено на отсутствие горизонтального overflow: все контейнеры на
`max-w-*` + адаптивные grid (`grid-cols-1 sm:… lg:…`), длинные строки — `truncate`
в списках. Живой визуальный прогон в браузере (пиксели на 360/390/768/1280/1440,
zoom 200%, реальная клавиатурная навигация) выполняется вручную на dev-стенде —
в CI-окружении без браузера не воспроизводится; блокеров по коду не выявлено.
