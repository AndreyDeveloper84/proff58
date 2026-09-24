# TASK_STATUS — задание владельца 24.09.2026

| ID | Статус | Проверка | Блокер |
|---|---|---|---|
| T1 Доставка без 0 ₽ | done | `pytest apps/delivery apps/integration_ship` — 45 passed; stub только при `SHIP_ALLOW_STUB=True` (dev), иначе `manual_required` (`provider_unavailable`); онлайн-оплата при `manual_required` уже запрещена сервером (`payments/api.py`) | Реальный СДЭК не реализован: нет договора/API-доступа/тарифных параметров |
| T2 Email и уведомления | done (код) | `pytest apps/notifications apps/orders/tests/test_customer_email.py apps/payments apps/leads apps/integration_max` — 257 passed; письма покупателю (заказ, статусы) и менеджерам (возврат) через существующий outbox; `_log` сделан идемпотентным; чеки 54-ФЗ шлёт АТОЛ Онлайн; runbook §11.1 | Реальная отправка не проверена: нет SMTP-доступа и тестового адреса; `STAFF_NOTIFICATION_EMAILS`, `EMAIL_*`, `DEFAULT_FROM_EMAIL` задаёт владелец |
