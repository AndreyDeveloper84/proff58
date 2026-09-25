# apps/core

Ядро платформы. Сейчас содержит **реестр доменных событий** (`events.py`).
Позже сюда добавятся `SiteSettings` и `features`/`is_enabled()` (#59).

## Доменные события (`events.py`)

Единый контракт событий платформы. Издатель эмитит факт, подписчики реагируют,
издатель о них не знает — это развязывает магазин, CRM, AI, уведомления и
интеграции.

### Правила
1. **Все сигналы — только в `apps/core/events.py`.** Новый сигнал заводится тут и
   только с ADR (`docs/adr/`, см. #77).
2. **Эмит — из use-case (сервисный слой) или admin-flow, не через `model.post_save`.**
   Иначе события дублируются и теряют контекст (`source`/`changed_fields`).
3. **Эмит через `transaction.on_commit(...)`** — подписчик должен видеть
   закоммиченные данные.

### Подписка (когда появятся слушатели)
Обработчик кладётся в `receivers.py` приложения-подписчика и подключается в его
`AppConfig.ready()`:

```python
# apps/<module>/apps.py
class SomeConfig(AppConfig):
    def ready(self):
        from . import receivers  # noqa: F401
```

```python
# apps/<module>/receivers.py
from django.dispatch import receiver
from apps.core.events import order_paid

@receiver(order_paid)
def on_order_paid(sender, order_id, payment_id, **kwargs):
    order = Order.objects.get(pk=order_id)  # перечитываем актуальное состояние из БД
    ...
```

Для опциональных модулей (CRM/AI) подписка — под feature-флагом (`core.features`,
#59).

### Payload — стабильные id, не инстансы
События несут идентификаторы и снапшоты (`product_id`, `user_id`, `changed_fields`,
`source`), а **не** живые ORM-инстансы: к моменту обработки (Celery/другой воркер)
инстанс может устареть, поэтому подписчик перечитывает объект из БД сам. Допустимые
значения `source` — в `core.events.EventSource`. Полный payload каждого события — в
docstring `events.py`.
