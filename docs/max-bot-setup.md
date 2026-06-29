# Настройка MAX-бота

Инструкция по регистрации бота, получению токена и настройке webhook
для интеграции магазина «Профессионал» с мессенджером MAX.

> Связанные документы: [ARCHITECTURE.md](ARCHITECTURE.md) (раздел `integration_max`),
> issue #47 (реализация webhook handler).

---

## 1. Регистрация бота

### 1.1 Подготовка

1. Зайти на [dev.max.ru](https://dev.max.ru) → раздел «Для партнёров»
2. Создать и верифицировать профиль организации (ИП или самозанятый)
3. Пройти модерацию

### 1.2 Создание бота

1. В панели партнёра создать нового бота
2. Указать название: `Профессионал` (или `Профессионал Dev` для staging)
3. Получить **токен бота** (access token)
4. Сохранить токен в `.env` (см. раздел 3)

> **Два бота:** для staging и production нужны отдельные боты с отдельными
> токенами, чтобы webhook-и не пересекались.

---

## 2. MAX Bot API — ключевые сведения

### 2.1 Базовый URL

```
https://platform-api2.max.ru
```

### 2.2 Авторизация

Токен передаётся в заголовке:

```
Authorization: <BOT_TOKEN>
```

### 2.3 Лимиты

- Максимум **30 запросов/сек** на `platform-api2.max.ru`
- Webhook: только **HTTPS** с сертификатом от доверенного CA

### 2.4 Основные методы

| Метод | Описание |
|-------|----------|
| `GET /me` | Информация о боте |
| `POST /subscriptions` | Подписка на webhook |
| `GET /subscriptions` | Текущие подписки |
| `DELETE /subscriptions` | Отписка |
| `POST /messages` | Отправка сообщения |
| `POST /answers` | Ответ на callback-кнопку |
| `GET /updates` | Long polling (только для dev) |

---

## 3. Конфигурация (.env)

Добавить в `.env` окружения:

```env
# MAX Bot
MAX_BOT_TOKEN=<токен бота из dev.max.ru>
MAX_WEBHOOK_SECRET=<случайный секрет для подписи, 32+ символов>
MAX_BOT_API_URL=https://platform-api2.max.ru
```

Переменные для staging и production **разные** (разные боты, разные токены).

---

## 4. Настройка webhook

### 4.1 Production / Staging

Webhook URL для подписки:

```
https://proff58.ru/api/max/webhook/         # production
https://dev.proff58.ru/api/max/webhook/      # staging
```

Подписаться через API:

```bash
curl -X POST https://platform-api2.max.ru/subscriptions \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://proff58.ru/api/max/webhook/",
    "update_types": ["bot_started", "message_created", "message_callback"]
  }'
```

### 4.2 Локальная разработка (ngrok)

```bash
# 1. Поднять dev-сервер
docker compose up -d

# 2. Запустить ngrok
ngrok http 8000

# 3. Подписаться на webhook с ngrok URL
curl -X POST https://platform-api2.max.ru/subscriptions \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<xxxx>.ngrok.io/api/max/webhook/",
    "update_types": ["bot_started", "message_created", "message_callback"]
  }'
```

### 4.3 Проверка подписки

```bash
curl -s https://platform-api2.max.ru/subscriptions \
  -H "Authorization: $MAX_BOT_TOKEN" | python3 -m json.tool
```

### 4.4 Удаление подписки

```bash
curl -X DELETE "https://platform-api2.max.ru/subscriptions?url=https://proff58.ru/api/max/webhook/" \
  -H "Authorization: $MAX_BOT_TOKEN"
```

---

## 5. Формат входящих событий (webhook payload)

MAX отправляет POST-запросы с JSON-телом на зарегистрированный URL.

### 5.1 bot_started — пользователь запустил бота

```json
{
  "update_type": "bot_started",
  "timestamp": 1718880000000,
  "chat_id": 12345678,
  "user": {
    "user_id": 87654321,
    "name": "Иван Иванов",
    "username": "ivan_ivanov"
  }
}
```

**Обработка:** сохранить `chat_id` для отправки уведомлений пользователю.

### 5.2 message_created — входящее сообщение

```json
{
  "update_type": "message_created",
  "timestamp": 1718880001000,
  "message": {
    "sender": {
      "user_id": 87654321,
      "name": "Иван Иванов"
    },
    "recipient": {
      "chat_id": 12345678,
      "chat_type": "dialog"
    },
    "body": {
      "mid": "mid.001",
      "seq": 1,
      "text": "Привет"
    }
  }
}
```

### 5.3 message_created с contact (после request_contact)

```json
{
  "update_type": "message_created",
  "timestamp": 1718880002000,
  "message": {
    "sender": {
      "user_id": 87654321,
      "name": "Иван Иванов"
    },
    "recipient": {
      "chat_id": 12345678,
      "chat_type": "dialog"
    },
    "body": {
      "mid": "mid.002",
      "seq": 2,
      "attachments": [
        {
          "type": "contact",
          "payload": {
            "vcf_info": "BEGIN:VCARD\r\nVERSION:3.0\r\nTEL;TYPE=cell:79001234567\r\nFN:Иван Иванов\r\nEND:VCARD\r\n",
            "max_info": {
              "user_id": 87654321
            },
            "hash": "a1b2c3d4e5f6..."
          }
        }
      ]
    }
  }
}
```

**Верификация контакта (HMAC-SHA256):**

```python
import hmac
import hashlib

def verify_contact(token: str, vcf_info: str, received_hash: str) -> bool:
    """Проверить подлинность контакта от MAX.
    
    vcf_info приходит с \\r\\n — перед хешированием
    заменить экранированные последовательности на реальные переносы.
    """
    vcf_bytes = vcf_info.replace("\\r\\n", "\r\n").encode("utf-8")
    expected = hmac.new(
        token.encode("utf-8"), vcf_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_hash)
```

### 5.4 message_callback — нажатие inline-кнопки

```json
{
  "update_type": "message_callback",
  "timestamp": 1718880003000,
  "callback": {
    "callback_id": "cb_123",
    "payload": "order_status:42",
    "user": {
      "user_id": 87654321,
      "name": "Иван Иванов"
    },
    "message": {
      "sender": {"user_id": 100},
      "recipient": {"chat_id": 12345678},
      "body": {"mid": "mid.003"}
    }
  }
}
```

**Ответ на callback:**

```bash
curl -X POST https://platform-api2.max.ru/answers \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"callback_id": "cb_123", "notification": "Готово!"}'
```

---

## 6. Отправка сообщений

### 6.1 Текстовое сообщение

```bash
curl -X POST https://platform-api2.max.ru/messages \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 12345678,
    "text": "Ваш заказ #42 оплачен!"
  }'
```

### 6.2 Сообщение с inline-кнопками

```bash
curl -X POST https://platform-api2.max.ru/messages \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 12345678,
    "text": "Поделитесь номером телефона для привязки аккаунта:",
    "attachments": [{
      "type": "inline_keyboard",
      "payload": {
        "buttons": [[{
          "type": "request_contact",
          "text": "📱 Отправить номер"
        }]]
      }
    }]
  }'
```

### 6.3 OTP через кнопку clipboard

```bash
curl -X POST https://platform-api2.max.ru/messages \
  -H "Authorization: $MAX_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 12345678,
    "text": "Ваш код подтверждения: **4829**",
    "format": "markdown",
    "attachments": [{
      "type": "inline_keyboard",
      "payload": {
        "buttons": [[{
          "type": "clipboard",
          "text": "📋 Скопировать код",
          "payload": "4829"
        }]]
      }
    }]
  }'
```

---

## 7. Параметры для staging и production

| Параметр | Staging | Production |
|----------|---------|------------|
| Бот | Отдельный dev-бот | Отдельный prod-бот |
| `MAX_BOT_TOKEN` | Dev-токен | Prod-токен |
| `MAX_WEBHOOK_SECRET` | Уникальный секрет | Уникальный секрет |
| Webhook URL | `https://dev.proff58.ru/api/max/webhook/` | `https://proff58.ru/api/max/webhook/` |
| HTTPS | Let's Encrypt (auto) | Коммерческий cert (reg.ru) |

---

## 8. Чек-лист проверки

- [ ] Бот зарегистрирован на dev.max.ru
- [ ] Токен получен и сохранён в `.env` (не в git)
- [ ] Webhook подписан (`POST /subscriptions`)
- [ ] `GET /me` возвращает информацию о боте
- [ ] `GET /subscriptions` показывает URL сервера
- [ ] Бот отвечает на `/start` (событие `bot_started`)
- [ ] Кнопка `request_contact` отправляет контакт
- [ ] HMAC-SHA256 верификация проходит
- [ ] Кнопка `clipboard` копирует текст
