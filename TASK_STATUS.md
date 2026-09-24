# TASK_STATUS — задание владельца 24.09.2026

| ID | Статус | Проверка | Блокер |
|---|---|---|---|
| T1 Доставка без 0 ₽ | done | `pytest apps/delivery apps/integration_ship` — 45 passed; stub только при `SHIP_ALLOW_STUB=True` (dev), иначе `manual_required` (`provider_unavailable`); онлайн-оплата при `manual_required` уже запрещена сервером (`payments/api.py`) | Реальный СДЭК не реализован: нет договора/API-доступа/тарифных параметров |
