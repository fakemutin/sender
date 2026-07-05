import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from telethon import TelegramClient

from broadcaster import CycleStats, list_allowed_chats, run_broadcast_cycle
from config import AccountSettings, AppConfig

logger = logging.getLogger(__name__)
LOCK_DIR = Path("locks")


def _lock_path(session_name: str) -> Path:
    safe_name = session_name.replace("/", "_").replace("\\", "_")
    return LOCK_DIR / f"{safe_name}.lock"


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_account_lock(session_name: str) -> Path | None:
    LOCK_DIR.mkdir(exist_ok=True)
    lock_file = _lock_path(session_name)

    if lock_file.exists():
        try:
            pid = int(lock_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = -1

        if pid > 0 and _is_process_alive(pid):
            logger.warning("Аккаунт %s уже запущен (pid %s), пропуск", session_name, pid)
            return None

        lock_file.unlink(missing_ok=True)

    lock_file.write_text(str(os.getpid()), encoding="utf-8")
    return lock_file


def release_account_lock(lock_file: Path | None) -> None:
    if lock_file and lock_file.exists():
        lock_file.unlink(missing_ok=True)


def create_client(account: AccountSettings) -> TelegramClient:
    return TelegramClient(
        account.session_name,
        account.api_id,
        account.api_hash,
        connection_retries=2,
        retry_delay=1,
        sequential_updates=True,
    )


@asynccontextmanager
async def account_session(account: AccountSettings):
    lock_file = acquire_account_lock(account.session_name)
    if lock_file is None:
        yield None
        return

    client = create_client(account)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("[%s] Сессия не авторизована: %s", account.name, account.session_name)
            yield None
            return

        me = await client.get_me()
        logger.info(
            "[%s] Подключён: %s (@%s)",
            account.name,
            me.first_name,
            me.username or "без username",
        )
        yield client
    finally:
        await client.disconnect()
        release_account_lock(lock_file)


async def run_account_list(account: AccountSettings) -> int:
    async with account_session(account) as client:
        if client is None:
            return 0
        return await list_allowed_chats(client, account)


async def run_account_once(account: AccountSettings) -> CycleStats:
    async with account_session(account) as client:
        if client is None:
            return CycleStats(skipped=1)
        return await run_broadcast_cycle(client, account)


async def run_all_accounts_once(config: AppConfig, accounts: tuple[AccountSettings, ...]) -> None:
    total = CycleStats()

    for index, account in enumerate(accounts):
        stats = await run_account_once(account)
        total.sent += stats.sent
        total.failed += stats.failed
        total.skipped += stats.skipped

        if index < len(accounts) - 1 and stats.skipped == 0:
            logger.info(
                "Пауза %s сек перед следующим аккаунтом...",
                config.delay_between_accounts,
            )
            await asyncio.sleep(config.delay_between_accounts)

    logger.info(
        "Итого: отправлено %s, ошибок %s, пропущено аккаунтов %s",
        total.sent,
        total.failed,
        total.skipped,
    )


async def run_all_accounts_list(accounts: tuple[AccountSettings, ...]) -> None:
    total = 0
    for account in accounts:
        total += await run_account_list(account)
    print(f"\nВсего разрешённых чатов: {total}")


async def run_loop(config: AppConfig, accounts: tuple[AccountSettings, ...], once: bool) -> None:
    while True:
        await run_all_accounts_once(config, accounts)

        if once:
            break

        logger.info(
            "Все аккаунты отработали. Следующий цикл через %s сек (%s ч)",
            config.break_after_cycle,
            round(config.break_after_cycle / 3600, 1),
        )
        await asyncio.sleep(config.break_after_cycle)
