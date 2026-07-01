# Catalog Governance: разделение владения сайт / 1С

## Принцип

| Область | Мастер | Что НЕ делает другой |
|---------|--------|----------------------|
| Цена, остаток, `code_1c`, артикул | **1С** | Сайт не правит цены/остатки напрямую |
| Дерево категорий, SEO, витринное имя, фото, описание, публикация | **Сайт** | Импорт из 1С не перезаписывает контентные поля |

## Защита контента (`content_locked`)

Поле `Product.content_locked = True` запрещает любым автоматическим процессам (импорт 1С, enrich-команды, image pipeline) изменять витринные поля: `name`, `description`, `images`, EAV-атрибуты.

Проверяется в:
- `import_products` (`Command._apply`) — витринное `name` не меняется при `content_locked=True`
- `enrich_attributes`, `enrich_tool_type` — гард в `enrichment/apply.py`
- `image_pipeline.py` — гард при сохранении фото

Тесты: `test_enrichment_apply.py::test_content_locked_blocks_everything`, `test_provenance.py::test_apply_blocked_by_content_locked`, `test_image_pipeline.py::test_content_locked_blocks`.

## Маппинг групп 1С → категории сайта

`data/group_mapping.json` — таблица `external_id` группы 1С → `site_path` (путь категории на сайте).

- Ключ маппинга — `external_id` группы (устойчивый ID 1С), а не имя (имена дублируются).
- `on_site: false` → товары идут в корень «Не на сайте» (offsite), не на витрину.
- Категория назначается автоматически при первом импорте; при `category_is_manual=True` автоимпорт категорию не меняет.

## uncategorized → модерация

Товары без маппинга (`unmatched_group`) получают `status=IMPORTED, is_active=False`. Они не видны на витрине (каталог-API фильтрует `is_active=True`). Менеджер разбирает через `ImportRun` в админке.

## Ссылки

- `apps/catalog/management/commands/import_products.py` — импорт 1С
- `apps/catalog/models.py` — поля `content_locked`, `category_is_manual`
- `docs/ARCHITECTURE.md` §2 — слои и границы модулей
- `docs/1c-api-spec.md` — контракт приёма данных от 1С
