import asyncio
import html
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from account_auth import auth_manager
from admin_account_flow import (
    AddAccount,
    cmd_addaccount,
    on_add_api_hash,
    on_add_api_id,
    on_add_name,
    on_add_password,
    on_add_phone,
    on_add_proxy,
    on_auth_cancel,
    on_auth_digit,
    on_session_file,
)
from blocked_chats import blocked_count, estimate_accounts
from config import load_app_config
from import_chats import import_from_text
from proxy import parse_socks5_proxy
from storage import (
    append_allowed_chats,
    chat_counts,
    find_account,
    get_admin_ids,
    load_accounts_raw,
    load_state,
    save_state,
    update_account,
    update_defaults,
)
from text_utils import extract_chat_tokens, mask_proxy_string, parse_chat_text, proxy_to_string

logger = logging.getLogger(__name__)
MAIN_SCRIPT = Path(__file__).resolve().parent / "main.py"
SEP = "────────────────────"


def _is_admin(user_id: int) -> bool:
    admins = get_admin_ids()
    return not admins or user_id in admins


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статус", callback_data="status"),
                InlineKeyboardButton(text="▶️ Запуск", callback_data="run"),
            ],
            [
                InlineKeyboardButton(text="👤 Аккаунты", callback_data="accounts"),
                InlineKeyboardButton(text="🧹 Фильтр", callback_data="filter"),
            ],
            [
                InlineKeyboardButton(text="🧮 Аккаунты?", callback_data="calc"),
                InlineKeyboardButton(text="➕ Аккаунт", callback_data="add_account"),
            ],
            [
                InlineKeyboardButton(text="📖 Справка", callback_data="help"),
            ],
        ]
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu")]]
    )


def _welcome_text() -> str:
    return (
        "📡 <b>TG Broadcast</b>\n"
        f"{SEP}\n"
        "Панель управления рассылкой.\n"
        "Выберите действие 👇"
    )


def _session_ok(session_name: str) -> bool:
    return Path(f"{session_name}.session").exists()


def _format_status() -> str:
    state = load_state()
    last = state.get("last_run", "ещё не запускали")
    last_icon = "✅" if last == "ok" else "⏳" if "error" not in str(last) else "❌"

    try:
        config = load_app_config()
        sessions_ok = sum(1 for a in config.accounts if _session_ok(a.session_name))
        mode = "параллельно ⚡" if config.parallel_accounts else "по очереди 🐢"

        lines = [
            "📊 <b>Статус системы</b>",
            SEP,
            f"🕐 Запуск: {last_icon} <code>{html.escape(str(last))}</code>",
            f"👤 Аккаунтов: <b>{len(config.accounts)}</b>",
            f"🔐 Сессии: <b>{sessions_ok}/{len(config.accounts)}</b>",
            f"⚙️ Режим: {mode}",
            f"📁 Чатов в базе: <b>{chat_counts()['chats']}</b>",
            f"📂 Addlist-папок: <b>{chat_counts()['addlists']}</b>",
            f"🚫 В блоке: <b>{blocked_count()}</b> чатов",
            "",
        ]

        for account in config.accounts:
            icon = "🟢" if account.enabled else "⚫"
            sess = "✅" if _session_ok(account.session_name) else "❌"
            proxy = mask_proxy_string(account.proxy.label()) if account.proxy else "нет"
            lines += [
                f"{icon} <b>{html.escape(account.name)}</b>  {sess}",
                f"   📱 <code>{html.escape(account.session_name)}</code>",
                f"   📢 @{html.escape(account.source_chat)} · пост <b>#{account.source_message_id}</b>",
                f"   🧦 <code>{html.escape(proxy)}</code>",
                "",
            ]

        if sessions_ok < len(config.accounts):
            lines.append("⚠️ <i>Нет .session файла — авторизуйте аккаунт на сервере.</i>")

        return "\n".join(lines)
    except Exception as exc:
        return (
            "📊 <b>Статус системы</b>\n"
            f"{SEP}\n"
            f"❌ <b>Ошибка конфига</b>\n<code>{html.escape(str(exc))}</code>\n\n"
            "<i>Заполните .env или accounts.json</i>"
        )


def _format_accounts() -> str:
    try:
        config = load_app_config()
        lines = ["👤 <b>Аккаунты</b>", SEP, ""]
        for i, account in enumerate(config.accounts, 1):
            icon = "🟢" if account.enabled else "⚫"
            proxy = mask_proxy_string(account.proxy.label()) if account.proxy else "—"
            lines += [
                f"<b>{i}. {icon} {html.escape(account.name)}</b>",
                f"   session · <code>{html.escape(account.session_name)}</code>",
                f"   source · @{html.escape(account.source_chat)} #{account.source_message_id}",
                f"   proxy  · <code>{html.escape(proxy)}</code>",
                f"   delay  · {account.delay_between_chats} сек",
                "",
            ]
        return "\n".join(lines)
    except Exception as exc:
        return f"❌ {html.escape(str(exc))}"


def _help_text() -> str:
    return (
        "📖 <b>Справка</b>\n"
        f"{SEP}\n\n"
        "<b>Кнопки</b>\n"
        "📊 Статус — состояние системы\n"
        "▶️ Запуск — один цикл рассылки\n"
        "👤 Аккаунты — список аккаунтов\n\n"
        "<b>Команды</b>\n"
        "<code>/proxy acc1 socks5://user:pass@1.2.3.4:1080</code>\n"
        "<code>/source channel 13</code>\n"
        "<code>/source acc1 channel 13</code>\n"
        "<code>/toggle acc1</code>\n"
        "<code>/delay 120</code>\n\n"
        "<b>Аккаунты</b>\n"
        "<code>/addaccount</code> — добавить через код (римские цифры)\n"
        "Или отправьте <b>.session</b> файл:\n"
        "<code>acc1 API_ID API_HASH [socks5://...]</code>\n\n"
        "<b>Фильтр</b>\n"
        "🧹 или <code>/filter</code> — проверить чаты, мёртвые в блок\n"
        "<b>Калькулятор</b>\n"
        "<code>/calc 3000</code> — сколько аккаунтов нужно\n\n"
        "<b>Файл .txt</b>\n"
        "Отправьте список чатов или вставьте текст с t.me ссылками.\n"
        "Подпись: <code>acc1</code> или пусто."
    )


def _format_import_result(info: dict) -> str:
    return (
        "✅ <b>База обновлена</b>\n"
        f"{SEP}\n"
        f"🔗 URL в тексте: <b>{info['raw_urls']}</b>\n"
        f"➕ Новых чатов: <b>{info['new_chats']}</b>\n"
        f"➕ Новых addlist: <b>{info['new_addlists']}</b>\n"
        f"📁 Всего чатов: <b>{info['total_chats']}</b>\n"
        f"📂 Всего addlist: <b>{info['total_addlists']}</b>\n"
        f"🎯 Куда: <code>{html.escape(info['target'])}</code>"
    )


def _format_run_result(code: int, output: str) -> str:
    icon = "✅" if code == 0 else "❌"
    status = "Успешно" if code == 0 else f"Ошибка (код {code})"

    important = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(k in line for k in ("✓", "✗", "Итого", "ERROR", "Подключён", "отправлено", "FloodWait")):
            important.append(line)

    body = "\n".join(html.escape(x) for x in important[-15:]) if important else html.escape(output[-1500:])
    if not body.strip():
        body = "<i>Нет вывода</i>"

    return (
        f"{icon} <b>{status}</b>\n"
        f"{SEP}\n"
        f"<pre>{body}</pre>"
    )


async def _run_subcommand(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(MAIN_SCRIPT),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(MAIN_SCRIPT.parent),
        env=os.environ.copy(),
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace")


async def _run_broadcast() -> tuple[int, str]:
    return await _run_subcommand("--once")


async def _run_filter() -> tuple[int, str]:
    return await _run_subcommand("--filter-chats")


async def _answer(message: Message, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    await message.answer(text, reply_markup=keyboard)


async def _edit_or_send(query: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    try:
        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await query.message.answer(text, reply_markup=keyboard)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    async def deny(message: Message) -> None:
        await message.answer("🚫 Нет доступа.")

    @dp.message(Command("start", "menu"))
    async def cmd_start(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            await deny(message)
            return
        await _answer(message, _welcome_text(), _menu_keyboard())

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await _answer(message, _help_text(), _back_keyboard())

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await _answer(message, _format_status(), _back_keyboard())

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await _answer(message, _format_accounts(), _back_keyboard())

    @dp.message(Command("filter"))
    async def cmd_filter(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        wait = await message.answer("🧹 <b>Фильтрую чаты...</b>\n<i>Мёртвые попадут в блок-лист</i>")
        code, output = await _run_filter()
        save_state({
            **load_state(),
            "last_filter": "ok" if code == 0 else f"error ({code})",
            "last_filter_output": output,
            "last_filter_at": datetime.now().isoformat(timespec="seconds"),
        })
        await wait.edit_text(_format_run_result(code, output), reply_markup=_back_keyboard())

    @dp.message(Command("calc"))
    async def cmd_calc(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await _answer(
                message,
                "❌ Формат: <code>/calc 3000</code>\n\n"
                "<i>750 чатов на аккаунт (Premium лимит ~1000, с запасом)</i>",
                _back_keyboard(),
            )
            return
        try:
            total = int(parts[1])
        except ValueError:
            await _answer(message, "❌ Укажите число чатов", _back_keyboard())
            return
        info = estimate_accounts(total)
        await _answer(
            message,
            (
                "🧮 <b>Калькулятор аккаунтов</b>\n"
                f"{SEP}\n"
                f"📁 Чатов: <b>{info['total']}</b>\n"
                f"👤 Нужно аккаунтов: <b>{info['accounts']}</b>\n"
                f"📊 Лимит на аккаунт: <b>{info['per_account']}</b>\n"
                f"🧦 С прокси: <b>{info['with_proxy']}</b>\n"
                f"🌐 Без прокси: <b>{info['without_proxy']}</b>"
            ),
            _back_keyboard(),
        )

    @dp.message(Command("addaccount"))
    async def cmd_addaccount_handler(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await cmd_addaccount(message, state)

    @dp.message(AddAccount.name)
    async def fsm_add_name(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_name(message, state)

    @dp.message(AddAccount.phone)
    async def fsm_add_phone(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_phone(message, state)

    @dp.message(AddAccount.api_id)
    async def fsm_add_api_id(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_api_id(message, state)

    @dp.message(AddAccount.api_hash)
    async def fsm_add_api_hash(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_api_hash(message, state)

    @dp.message(AddAccount.proxy)
    async def fsm_add_proxy(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_proxy(message, state)

    @dp.message(AddAccount.password)
    async def fsm_add_password(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await on_add_password(message, state)

    @dp.callback_query(F.data.startswith("auth_digit:"))
    async def cb_auth_digit(query: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await on_auth_digit(query, state)

    @dp.callback_query(F.data == "auth_cancel")
    async def cb_auth_cancel(query: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await on_auth_cancel(query, state)

    @dp.callback_query(F.data == "add_account")
    async def cb_add_account(query: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await query.answer()
        await cmd_addaccount(query.message, state)

    @dp.message(Command("run"))
    async def cmd_run(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        wait = await message.answer("⏳ <b>Запускаю рассылку...</b>\n<i>Это может занять время</i>")
        code, output = await _run_broadcast()
        save_state({
            **load_state(),
            "last_run": "ok" if code == 0 else f"error ({code})",
            "last_output": output,
            "last_run_at": datetime.now().isoformat(timespec="seconds"),
        })
        await wait.edit_text(_format_run_result(code, output), reply_markup=_back_keyboard())

    @dp.message(Command("proxy"))
    async def cmd_proxy(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await _answer(message, "❌ Формат:\n<code>/proxy acc1 socks5://user:pass@host:1080</code>", _back_keyboard())
            return
        name, proxy_raw = parts[1], parts[2].strip()
        try:
            proxy = parse_socks5_proxy(proxy_raw, account_name=name)
            update_account(name, proxy=proxy_to_string(proxy))
            await _answer(
                message,
                f"✅ Прокси обновлён\n{SEP}\n👤 <b>{html.escape(name)}</b>\n🧦 <code>{html.escape(mask_proxy_string(proxy_raw))}</code>",
                _back_keyboard(),
            )
        except Exception as exc:
            await _answer(message, f"❌ {html.escape(str(exc))}", _back_keyboard())

    @dp.message(Command("source"))
    async def cmd_source(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split()
        try:
            if len(parts) == 3:
                _, chat, msg_id = parts
                update_defaults(source_chat=chat.lstrip("@"), source_message_id=int(msg_id))
                await _answer(message, f"✅ Источник (defaults)\n📢 @{html.escape(chat.lstrip('@'))} · #{msg_id}", _back_keyboard())
            elif len(parts) == 4:
                _, name, chat, msg_id = parts
                update_account(name, source_chat=chat.lstrip("@"), source_message_id=int(msg_id))
                await _answer(
                    message,
                    f"✅ Источник\n👤 <b>{html.escape(name)}</b>\n📢 @{html.escape(chat.lstrip('@'))} · #{msg_id}",
                    _back_keyboard(),
                )
            else:
                await _answer(message, "❌ <code>/source channel 13</code>\n<code>/source acc1 channel 13</code>", _back_keyboard())
        except Exception as exc:
            await _answer(message, f"❌ {html.escape(str(exc))}", _back_keyboard())

    @dp.message(Command("toggle"))
    async def cmd_toggle(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await _answer(message, "❌ <code>/toggle acc1</code>", _back_keyboard())
            return
        name = parts[1].strip()
        account = find_account(load_accounts_raw(), name)
        if account is None:
            await _answer(message, "❌ Аккаунт не найден", _back_keyboard())
            return
        new_value = not account.get("enabled", True)
        update_account(name, enabled=new_value)
        icon = "🟢 включён" if new_value else "⚫ выключен"
        await _answer(message, f"✅ <b>{html.escape(name)}</b> — {icon}", _back_keyboard())

    @dp.message(Command("delay"))
    async def cmd_delay(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await _answer(message, "❌ <code>/delay 120</code>", _back_keyboard())
            return
        seconds = int(parts[1])
        update_defaults(delay_between_chats=seconds)
        await _answer(message, f"✅ Пауза между чатами: <b>{seconds}</b> сек", _back_keyboard())

    @dp.callback_query(F.data == "menu")
    async def cb_menu(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫 Нет доступа", show_alert=True)
            return
        await _edit_or_send(query, _welcome_text(), _menu_keyboard())
        await query.answer()

    @dp.callback_query(F.data == "status")
    async def cb_status(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(query, _format_status(), _back_keyboard())
        await query.answer()

    @dp.callback_query(F.data == "accounts")
    async def cb_accounts(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(query, _format_accounts(), _back_keyboard())
        await query.answer()

    @dp.callback_query(F.data == "help")
    async def cb_help(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(query, _help_text(), _back_keyboard())
        await query.answer()

    @dp.callback_query(F.data == "filter")
    async def cb_filter(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(query, "🧹 <b>Фильтрую чаты...</b>\n<i>Подождите</i>", None)
        await query.answer()
        code, output = await _run_filter()
        save_state({
            **load_state(),
            "last_filter": "ok" if code == 0 else f"error ({code})",
            "last_filter_output": output,
            "last_filter_at": datetime.now().isoformat(timespec="seconds"),
        })
        await _edit_or_send(query, _format_run_result(code, output), _back_keyboard())

    @dp.callback_query(F.data == "calc")
    async def cb_calc(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(
            query,
            (
                "🧮 <b>Калькулятор</b>\n"
                f"{SEP}\n"
                "Отправьте команду:\n"
                "<code>/calc 3000</code>\n\n"
                "<b>Ориентиры для вашей базы</b>\n"
                "• 3 000 чатов → <b>4</b> аккаунта\n"
                "• 7 500 чатов → <b>10</b> аккаунтов\n"
                "• 15 000 чатов → <b>20</b> аккаунтов\n"
                "• 30 000 чатов → <b>40</b> аккаунтов\n\n"
                "<i>750 рабочих чатов на аккаунт (Premium ~1000, с запасом)</i>"
            ),
            _back_keyboard(),
        )
        await query.answer()

    @dp.callback_query(F.data == "run")
    async def cb_run(query: CallbackQuery) -> None:
        if not _is_admin(query.from_user.id):
            await query.answer("🚫", show_alert=True)
            return
        await _edit_or_send(query, "⏳ <b>Запускаю рассылку...</b>\n<i>Подождите</i>", None)
        await query.answer()
        code, output = await _run_broadcast()
        save_state({
            **load_state(),
            "last_run": "ok" if code == 0 else f"error ({code})",
            "last_output": output,
            "last_run_at": datetime.now().isoformat(timespec="seconds"),
        })
        await _edit_or_send(query, _format_run_result(code, output), _back_keyboard())

    @dp.message(F.document)
    async def on_document(message: Message, bot: Bot, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        if await on_session_file(message, bot, state):
            return
        if not message.document.file_name.lower().endswith(".txt"):
            await _answer(message, "❌ Нужен файл <b>.txt</b> или <b>.session</b>", _back_keyboard())
            return

        file = await bot.get_file(message.document.file_id)
        buffer = await bot.download_file(file.file_path)
        text = buffer.read().decode("utf-8", errors="replace")
        target = (message.caption or "").strip() or None
        info = import_from_text(text, target=target)
        await _answer(message, _format_import_result(info), _back_keyboard())

    @dp.message(F.text)
    async def on_text(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        text = message.text or ""
        if text.startswith("/"):
            return
        current = await state.get_state()
        if current:
            return
        parsed = parse_chat_text(text)
        if not parsed["chats"] and not parsed["addlists"]:
            return
        info = import_from_text(text)
        await _answer(message, _format_import_result(info), _back_keyboard())

    return dp


async def run_admin_bot() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Укажите BOT_TOKEN в .env")

    if not get_admin_ids():
        logger.warning("ADMIN_IDS пуст — бот доступен всем")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.delete_webhook(drop_pending_updates=True)
    dp = create_dispatcher()

    watch_proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(MAIN_SCRIPT),
        "--watch",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=str(MAIN_SCRIPT.parent),
        env=os.environ.copy(),
    )
    logger.info("Watch-процесс запущен (pid %s)", watch_proc.pid)

    logger.info("Admin bot запущен")
    try:
        await dp.start_polling(bot)
    finally:
        watch_proc.terminate()
