# TG Broadcast

Рассылка с обычного Telegram-аккаунта (Telethon) **только в чаты, где разрешена отправка**.

## Возможности

- Проверка прав перед отправкой (админ / send_messages)
- Пропуск личных чатов
- Белый список `ALLOWED_CHATS`
- Обработка FloodWait
- `--list` — предпросмотр разрешённых чатов
- `--once` — один цикл без паузы между циклами

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
# заполните .env
```

## Запуск

```bash
python main.py --list   # куда можно слать
python main.py --once   # один цикл
python main.py          # бесконечный цикл
```

## Конфиг (.env)

| Переменная | Описание |
|---|---|
| `API_ID`, `API_HASH` | [my.telegram.org](https://my.telegram.org) |
| `SESSION_NAME` | Имя файла сессии (номер телефона) |
| `SOURCE_CHAT` | Канал-источник (@username) |
| `SOURCE_MESSAGE_ID` | ID поста для рассылки |
| `REQUIRE_ADMIN` | `true` = только чаты где вы админ |
| `ALLOWED_CHATS` | Опциональный белый список |
| `DELAY_BETWEEN_CHATS` | Пауза между чатами (сек) |
| `BREAK_AFTER_CYCLE` | Пауза между циклами (сек) |

## Безопасность

- Не коммитьте `.env` и `*.session`
- Используйте только в своих группах/каналах
