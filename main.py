#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys

from dataclasses import replace

from config import filter_accounts, load_app_config
from runner import run_all_accounts_list, run_loop

logging.getLogger("telethon").setLevel(logging.CRITICAL)

logging.basicConfig(
    level=getattr(logging, __import__("os").getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("broadcast")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Лёгкая рассылка с 2+ user-аккаунтов только в разрешённые чаты",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Показать разрешённые чаты для выбранных аккаунтов",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Один цикл по всем аккаунтам и выход (удобно для cron)",
    )
    parser.add_argument(
        "--account",
        action="append",
        metavar="NAME",
        help="Запустить только указанный аккаунт (можно несколько раз)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Запускать аккаунты по очереди, а не параллельно",
    )
    parser.add_argument(
        "--bot",
        action="store_true",
        help="Запустить Telegram-бота для настройки и управления",
    )
    args = parser.parse_args()

    if args.bot:
        from admin_bot import run_admin_bot

        asyncio.run(run_admin_bot())
        return

    try:
        config = load_app_config()
        if args.sequential:
            config = replace(config, parallel_accounts=False)
        accounts = filter_accounts(config, set(args.account) if args.account else None)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    mode = "параллельно" if config.parallel_accounts else "по очереди"
    logger.info(
        "Аккаунтов в работе (%s): %s",
        mode,
        ", ".join(account.name for account in accounts),
    )

    if args.list:
        asyncio.run(run_all_accounts_list(config, accounts))
    else:
        asyncio.run(run_loop(config, accounts, once=args.once))


if __name__ == "__main__":
    main()
