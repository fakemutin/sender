import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import filter_accounts, load_app_config
from proxy import parse_socks5_proxy
from storage import (
    append_allowed_chats,
    find_account,
    get_admin_ids,
    load_accounts_raw,
    load_state,
    save_state,
    set_global_field,
    update_account,
    update_defaults,
)
from text_utils import extract_chat_tokens, mask_proxy_string, proxy_to_string

logger = logging.getLogger(__name__)

MAIN_SCRIPT = Path(__file__).resolve().parent / "main.py"


def _is_admin(user_id: int) -> bool:
    admins = get_admin_ids()
    return not admins or user_id in admins


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статус", callback_data="status"),
                InlineKeyboardButton(text="▶️ Запуск", callback_data="run"),
            ],
            [
                InlineKeyboardButton(text="📋 Аккаунты", callback_data="accounts"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
            ],
        ]
    )


def _format_accounts_summary() -> str:
    try:
        payload = load_accounts_raw()
    except Exception as exc:
        return f"Ошибка чтения accounts.json: {exc}"

    lines = [
        f"parallel: {payload.get('parallel_accounts', True)}",
        f"delay_between_chats(default): {payload.get('defaults', {}).get('delay_between_chats', '—')}",
        "",
    ]
    for account in payload.get("accounts", []):
        proxy = account.get("proxy") or "—"
        if isinstance(proxy, str):
            proxy = mask_proxy_string(proxy)
        status = "✅" if account.get("enabled", True) else "⏸"
        lines.append(
            f"{status} <b>{account.get('name')}</b>\n"
            f"  session: <code>{account.get('session_name')}</code>\n"
            f"  source: {account.get('source_chat')} #{account.get('source_message_id')}\n"
            f"  proxy: <code>{proxy}</code>"
        )
    return "\n".join(lines) if lines else "accounts.json пуст"


def _help_text() -> str:
    return (
        "<b>Команды</b>\n"
        "/start — меню\n"
        "/status — статус\n"
        "/run — запуск рассылки\n"
        "/accounts — список аккаунтов\n\n"
        "<b>Настройка</b>\n"
        "<code>/proxy acc1 socks5://user:pass@1.2.3.4:1080</code>\n"
        "<code>/source acc1 channel 13</code>\n"
        "<code>/source channel 13</code> — для defaults\n"
        "<code>/toggle acc1</code> — вкл/выкл аккаунт\n"
        "<code>/delay 120</code> — пауза между чатами\n\n"
        "<b>Загрузка чатов</b>\n"
        "Пришлите .txt файл — бот вытащит @username и t.me/...\n"
        "Подпись: <code>acc1</code> или пусто для defaults"
    )


async def _run_broadcast_subprocess() -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(MAIN_SCRIPT),
        "--once",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(MAIN_SCRIPT.parent),
        env=os.environ.copy(),
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace")[-3500:]
    return proc.returncode or 0, output


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            await message.answer("Нет доступа.")
            return
        await message.answer(
            "Панель управления рассылкой.\nВыберите действие или /help",
            reply_markup=_main_keyboard(),
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(_help_text())

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        state = load_state()
        last = state.get("last_run", "ещё не запускали")
        await message.answer(f"<b>Статус</b>\n\nlast_run: {last}\n\n{_format_accounts_summary()}")

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(_format_accounts_summary())

    @dp.message(Command("run"))
    async def cmd_run(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer("Запускаю рассылку...")
        code, output = await _run_broadcast_subprocess()
        state = load_state()
        state["last_run"] = "ok" if code == 0 else f"error ({code})"
        state["last_output"] = output
        save_state(state)
        await message.answer(
            f"Готово ({'ok' if code == 0 else 'error'}).\n\n<pre>{output}</pre>"
        )

    @dp.message(Command("proxy"))
    async def cmd_proxy(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Формат: /proxy acc1 socks5://user:pass@host:1080")
            return
        name, proxy_raw = parts[1], parts[2].strip()
        try:
            proxy = parse_socks5_proxy(proxy_raw, account_name=name)
            update_account(name, proxy=proxy_to_string(proxy))
            await message.answer(f"Прокси для <b>{name}</b> обновлён.")
        except Exception as exc:
            await message.answer(f"Ошибка: {exc}")

    @dp.message(Command("source"))
    async def cmd_source(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split()
        if len(parts) == 3:
            _, chat, msg_id = parts
            update_defaults(source_chat=chat.lstrip("@"), source_message_id=int(msg_id))
            await message.answer(f"Defaults: {chat} #{msg_id}")
            return
        if len(parts) == 4:
            _, name, chat, msg_id = parts
            update_account(name, source_chat=chat.lstrip("@"), source_message_id=int(msg_id))
            await message.answer(f"{name}: {chat} #{msg_id}")
            return
        await message.answer("Формат: /source channel 13  или  /source acc1 channel 13")

    @dp.message(Command("toggle"))
    async def cmd_toggle(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: /toggle acc1")
            return
        name = parts[1].strip()
        payload = load_accounts_raw()
        account = find_account(payload, name)
        if account is None:
            await message.answer("Аккаунт не найден")
            return
        new_value = not account.get("enabled", True)
        update_account(name, enabled=new_value)
        await message.answer(f"{name}: {'включён' if new_value else 'выключен'}")

    @dp.message(Command("delay"))
    async def cmd_delay(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: /delay 120")
            return
        seconds = int(parts[1])
        update_defaults(delay_between_chats=seconds)
        await message.answer(f"delay_between_chats = {seconds}")

    @dp.callback_query(F.data == "status")
    async def cb_status(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("Нет доступа", show_alert=True)
            return
        await query.message.answer(_format_accounts_summary())
        await query.answer()

    @dp.callback_query(F.data == "accounts")
    async def cb_accounts(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("Нет доступа", show_alert=True)
            return
        await query.message.answer(_format_accounts_summary())
        await query.answer()

    @dp.callback_query(F.data == "help")
    async def cb_help(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("Нет доступа", show_alert=True)
            return
        await query.message.answer(_help_text())
        await query.answer()

    @dp.callback_query(F.data == "run")
    async def cb_run(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("Нет доступа", show_alert=True)
            return
        await query.message.answer("Запускаю рассылку...")
        code, output = await _run_broadcast_subprocess()
        state = load_state()
        state["last_run"] = "ok" if code == 0 else f"error ({code})"
        state["last_output"] = output
        save_state(state)
        await query.message.answer(
            f"Готово ({'ok' if code == 0 else 'error'}).\n\n<pre>{output}</pre>"
        )
        await query.answer()

    @dp.message(F.document)
    async def on_document(message: Message, bot: Bot) -> None:
        if not _is_admin(message.from_user.id):
            return
        if not message.document.file_name.lower().endswith(".txt"):
            await message.answer("Пришлите .txt файл")
            return

        file = await bot.get_file(message.document.file_id)
        buffer = await bot.download_file(file.file_path)
        text = buffer.read().decode("utf-8", errors="replace")
        chats = extract_chat_tokens(text)
        if not chats:
            await message.answer("В файле не найдено чатов")
            return

        account_name = (message.caption or "").strip() or None
        added = append_allowed_chats(account_name, chats)
        target = account_name or "defaults"
        await message.answer(f"Загружено {added} чатов в <b>{target}</b>.")

    return dp


async def run_admin_bot() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Укажите BOT_TOKEN в .env")

    admins = get_admin_ids()
    if not admins:
        logger.warning("ADMIN_IDS пуст — бот доступен всем (небезопасно)")

    bot = Bot(token=token)
    dp = create_dispatcher()
    logger.info("Admin bot запущен")
    await dp.start_polling(bot)
