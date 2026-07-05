# TG Broadcast

Лёгкая рассылка с **2+ обычных Telegram-аккаунтов** только в чаты, где разрешена отправка.

## Особенности

- **Несколько аккаунтов** через `accounts.json`
- **Минимальная нагрузка на сервер**:
  - аккаунты работают **по очереди**, не параллельно
  - подключение → рассылка → отключение для каждого аккаунта
  - чаты обрабатываются **потоково**, без загрузки всего списка в память
  - `--once` + cron вместо вечного процесса
- Проверка прав перед отправкой
- Lock-файлы — один аккаунт не запустится дважды

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
cp accounts.example.json accounts.json
# заполните .env и accounts.json
```

## Первый вход (для каждого аккаунта)

```bash
python -c "
from telethon.sync import TelegramClient
import os
from dotenv import load_dotenv
load_dotenv()
client = TelegramClient('+79001111111', int(os.environ['API_ID']), os.environ['API_HASH'])
client.start()
client.disconnect()
"
```

Повторите для каждого `session_name` из `accounts.json`.

## Запуск

```bash
# Предпросмотр чатов
python main.py --list

# Один цикл по всем аккаунтам (рекомендуется)
python main.py --once

# Только один аккаунт
python main.py --once --account acc1

# Бесконечный цикл (если нужен daemon)
python main.py
```

## Cron (лёгкий режим для сервера)

```cron
# Каждые 3 часа — один цикл, процесс завершается
0 */3 * * * cd /path/to/tg-broadcast && /usr/bin/python3 main.py --once >> broadcast.log 2>&1
```

## accounts.json

```json
{
  "delay_between_accounts": 300,
  "break_after_cycle": 10800,
  "defaults": {
    "delay_between_chats": 120,
    "require_admin": true
  },
  "accounts": [
    {
      "name": "acc1",
      "session_name": "+79001111111",
      "source_chat": "channel",
      "source_message_id": 13,
      "enabled": true
    },
    {
      "name": "acc2",
      "session_name": "+79002222222",
      "source_chat": "channel",
      "source_message_id": 13,
      "enabled": true
    }
  ]
}
```

## Безопасность

- Не коммитьте `.env`, `accounts.json`, `*.session`
- Используйте только в своих группах/каналах
