#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys

from telethon import TelegramClient

from broadcaster import list_allowed_chats, run_broadcast_cycle
from config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("broadcast")


async def run_loop(settings, once: bool) -> None:
    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)

    while True:
        try:
            await client.start()
            me = await client.get_me()
            logger.info(
                "Аккаунт: %s (@%s)",
                me.first_name,
                me.username or "без username",
            )

            await run_broadcast_cycle(client, settings)

            await client.disconnect()

            if once:
                break

            logger.info(
                "Цикл завершён. Следующий через %s сек (%s ч)",
                settings.break_after_cycle,
                round(settings.break_after_cycle / 3600, 1),
            )
            await asyncio.sleep(settings.break_after_cycle)

        except KeyboardInterrupt:
            logger.info("Остановка по Ctrl+C")
            break
        except Exception as exc:
            logger.exception("Ошибка цикла: %s", exc)
            try:
                await client.disconnect()
            except Exception:
                pass
            if once:
                raise
            await asyncio.sleep(30)


async def run_list(settings) -> None:
    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    await client.start()
    await list_allowed_chats(client, settings)
    await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Рассылка с user-аккаунта только в чаты, где разрешена отправка",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Показать чаты, куда можно отправлять, и выйти",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Один цикл рассылки без паузы BREAK_AFTER_CYCLE",
    )
    args = parser.parse_args()

    try:
        settings = load_settings()
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if args.list:
        asyncio.run(run_list(settings))
    else:
        asyncio.run(run_loop(settings, once=args.once))


if __name__ == "__main__":
    main()
