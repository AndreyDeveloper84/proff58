# SP2 · Дизайн-система витрины «Профессионал» (#39)

Базовый набор токенов и компонентов, снимающий дизайн-блокер для frontend-разработки
витрины MVP (#6). Живой эталон — страница `/demo/ui` (kitchen-sink).

## Принцип

Цвета, типографика и радиусы заданы **токенами** в `frontend/app/globals.css`
(CSS-переменные) и замаплены в Tailwind v4 через `@theme inline`. Компоненты
**никогда** не хардкодят цвета — только утилиты токенов (`bg-surface`, `text-ink`,
`border-line`, …). Перекраска экземпляра магазина = смена `--accent` / `--primary`
из `SiteSettings`, без правки компонентов.

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
