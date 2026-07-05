# TG Broadcast

Лёгкая рассылка с **2+ обычных Telegram-аккаунтов** только в чаты, где разрешена отправка.

## Особенности

- **Несколько аккаунтов** через `accounts.json`
- **Параллельный запуск** всех аккаунтов одновременно (`PARALLEL_ACCOUNTS=true`)
- **SOCKS5 прокси** — для 2+ аккаунтов у каждого свой прокси (обязательно)
- **Минимальная нагрузка на сервер**:
  - подключение → рассылка → отключение для каждого аккаунта
  - чаты обрабатываются **потоково**, без загрузки всего списка в память
  - `--once` + cron вместо вечного процесса
- Проверка прав перед отправкой
- Lock-файлы — один аккаунт не запустится дважды

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
# заполните .env (SESSION_NAME, SOURCE_CHAT, SOURCE_MESSAGE_ID, ...)
```

Для **2+ аккаунтов** дополнительно: `cp accounts.example.json accounts.json` и оставьте `SESSION_NAME` пустым.

## Первый вход

```bash
python -c "
from telethon.sync import TelegramClient
import os
from dotenv import load_dotenv
load_dotenv()
client = TelegramClient(os.environ['SESSION_NAME'], int(os.environ['API_ID']), os.environ['API_HASH'])
client.start()
client.disconnect()
"
```

Для `accounts.json` — повторите для каждого `session_name`.

## Запуск

```bash
# Предпросмотр чатов
python main.py --list

# Один цикл по всем аккаунтам (рекомендуется)
python main.py --once

# Только один аккаунт
python main.py --once --account acc1

# По очереди (старый режим)
python main.py --once --sequential

# Бесконечный цикл (если нужен daemon)
python main.py
```

## Cron (лёгкий режим для сервера)

```cron
# Каждые 3 часа — один цикл, процесс завершается
0 */3 * * * cd /path/to/tg-broadcast && /usr/bin/python3 main.py --once >> broadcast.log 2>&1
```

## Конфиг (.env) — основной способ

| Переменная | Описание |
|---|---|
| `API_ID`, `API_HASH` | [my.telegram.org](https://my.telegram.org) |
| `SESSION_NAME` | Имя файла сессии (номер телефона) |
| `SOURCE_CHAT` | Канал-источник (@username) |
| `SOURCE_MESSAGE_ID` | ID поста для рассылки |
| `DELAY_BETWEEN_CHATS` | Пауза между чатами (сек) |
| `BREAK_AFTER_CYCLE` | Пауза между циклами (сек) |
| `REQUIRE_ADMIN` | `true` = только чаты где вы админ |
| `ALLOWED_CHATS` | Опциональный белый список |
| `SOCKS5_PROXY` | SOCKS5 для одного аккаунта (опционально) |

## accounts.json — для 2+ аккаунтов

Если `SESSION_NAME` в `.env` **пустой**, используется `accounts.json`.
Значения из `.env` подставляются как defaults для всех аккаунтов.

**При 2+ включённых аккаунтах** — у каждого **обязателен свой SOCKS5** (только socks5):

```json
"proxy": {
  "host": "1.2.3.4",
  "port": 1080,
  "username": "user",
  "password": "pass"
}
```

Или строкой: `"proxy": "socks5://user:pass@1.2.3.4:1080"` (рекомендуется)

## Telegram-бот для настройки

```env
BOT_TOKEN=123456:ABC...
ADMIN_IDS=123456789
```

```bash
python main.py --bot
```

**Что умеет бот:**
- `/start` — меню с кнопками
- `/run` — запуск рассылки
- `/status`, `/accounts` — статус аккаунтов и прокси
- `/proxy acc1 socks5://user:pass@1.2.3.4:1080` — прокси строкой
- `/source channel 13` или `/source acc1 channel 13`
- `/toggle acc1` — вкл/выкл аккаунт
- `/delay 120` — пауза между чатами
- Отправить **.txt файл** — парсит чаты, подпись `acc1` или пусто для defaults

Бот редактирует `accounts.json` на сервере.

## Безопасность

- Не коммитьте `.env`, `accounts.json`, `*.session`
- Используйте только в своих группах/каналах
