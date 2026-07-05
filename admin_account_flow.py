import html
import os
import re
from pathlib import Path

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from account_auth import auth_manager
from roman_keypad import code_display, roman_keypad
from storage import add_account

SEP = "────────────────────"


class AddAccount(StatesGroup):
    name = State()
    phone = State()
    api_id = State()
    api_hash = State()
    proxy = State()
    code = State()
    password = State()


class SessionUpload(StatesGroup):
    waiting = State()


def _back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="auth_cancel")]]
    )


async def cmd_addaccount(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddAccount.name)
    await message.answer(
        "➕ <b>Добавление аккаунта</b>\n"
        f"{SEP}\n"
        "Шаг 1/5 — имя аккаунта\n"
        "Пример: <code>acc1</code>",
        reply_markup=_back(),
    )


async def on_add_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", name):
        await message.answer("❌ Имя: латиница, цифры, _- (2–32 символа)")
        return
    await state.update_data(name=name)
    await state.set_state(AddAccount.phone)
    await message.answer(
        "Шаг 2/5 — номер телефона\n"
        "Пример: <code>+79001234567</code>",
        reply_markup=_back(),
    )


async def on_add_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip().replace(" ", "")
    if not re.fullmatch(r"\+\d{10,15}", phone):
        await message.answer("❌ Формат: <code>+79001234567</code>")
        return
    await state.update_data(phone=phone)
    await state.set_state(AddAccount.api_id)
    await message.answer("Шаг 3/5 — <b>api_id</b>\n(my.telegram.org)", reply_markup=_back())


async def on_add_api_id(message: Message, state: FSMContext) -> None:
    try:
        api_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ api_id — число")
        return
    await state.update_data(api_id=api_id)
    await state.set_state(AddAccount.api_hash)
    await message.answer("Шаг 4/5 — <b>api_hash</b>", reply_markup=_back())


async def on_add_api_hash(message: Message, state: FSMContext) -> None:
    api_hash = (message.text or "").strip()
    if len(api_hash) < 16:
        await message.answer("❌ api_hash слишком короткий")
        return
    await state.update_data(api_hash=api_hash)
    await state.set_state(AddAccount.proxy)
    await message.answer(
        "Шаг 5/5 — SOCKS5 прокси\n"
        "<code>socks5://user:pass@host:1080</code>\n"
        "или <code>-</code> без прокси",
        reply_markup=_back(),
    )


async def on_add_proxy(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    proxy_raw = (message.text or "").strip()
    wait = await message.answer("📨 Отправляю код в Telegram...")

    try:
        await auth_manager.start(
            message.from_user.id,
            name=data["name"],
            phone=data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy_raw=proxy_raw if proxy_raw != "-" else None,
        )
    except Exception as exc:
        await wait.edit_text(f"❌ {html.escape(str(exc))}")
        await state.clear()
        return

    pending = auth_manager.get(message.from_user.id)
    if pending:
        pending.proxy_raw = proxy_raw if proxy_raw != "-" else None

    await state.update_data(proxy_raw=proxy_raw if proxy_raw != "-" else None)
    await state.set_state(AddAccount.code)
    await wait.edit_text(
        "🔐 <b>Код из Telegram</b>\n"
        f"{SEP}\n"
        f"📱 <code>{html.escape(data['phone'])}</code>\n"
        f"Код: {code_display('')}\n\n"
        "<i>Нажимайте римские цифры 👇</i>",
        reply_markup=roman_keypad(""),
    )


async def on_auth_digit(query: CallbackQuery, state: FSMContext) -> None:
    pending = auth_manager.get(query.from_user.id)
    if not pending:
        await query.answer("Сессия истекла — /addaccount", show_alert=True)
        return

    action = (query.data or "").split(":", 1)[1]
    code = pending.code

    if action == "del":
        pending.code = code[:-1]
    elif action == "ok":
        if len(pending.code) < 5:
            await query.answer("Минимум 5 цифр", show_alert=True)
            return
        await query.answer()
        try:
            result = await auth_manager.submit_code(query.from_user.id, pending.code)
        except Exception as exc:
            await query.message.edit_text(f"❌ {html.escape(str(exc))}")
            await state.clear()
            return

        if result == "password":
            await state.update_data(
                proxy_raw=pending.proxy_raw,
            )
            await state.set_state(AddAccount.password)
            await query.message.edit_text(
                "🔒 <b>2FA пароль</b>\n"
                f"{SEP}\n"
                "Отправьте пароль двухфакторной авторизации:",
            )
            return

        data = await state.get_data()
        add_account(
            data["name"],
            data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy=pending.proxy_raw if pending.proxy_raw not in (None, "-", "") else None,
        )
        await state.clear()
        await query.message.edit_text(
            f"✅ <b>Аккаунт добавлен</b>\n"
            f"{SEP}\n"
            f"👤 <b>{html.escape(data['name'])}</b>\n"
            f"📱 <code>{html.escape(data['phone'])}</code>\n"
            f"🔐 Сессия сохранена",
        )
        return
    else:
        if len(code) >= 8:
            await query.answer("Максимум 8 цифр", show_alert=True)
            return
        pending.code = code + action

    await query.answer()
    data = await state.get_data()
    await query.message.edit_text(
        "🔐 <b>Код из Telegram</b>\n"
        f"{SEP}\n"
        f"📱 <code>{html.escape(data.get('phone', ''))}</code>\n"
        f"Код: {code_display(pending.code)}\n\n"
        "<i>Нажимайте римские цифры 👇</i>",
        reply_markup=roman_keypad(pending.code),
    )


async def on_add_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    data = await state.get_data()
    try:
        await auth_manager.submit_password(message.from_user.id, password)
    except Exception as exc:
        await message.answer(f"❌ {html.escape(str(exc))}")
        return

    add_account(
        data["name"],
        data["phone"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        proxy=data.get("proxy_raw") if data.get("proxy_raw") not in (None, "-") else None,
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Аккаунт добавлен</b>\n"
        f"{SEP}\n"
        f"👤 <b>{html.escape(data['name'])}</b>\n"
        f"📱 <code>{html.escape(data['phone'])}</code>",
    )


async def on_auth_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await auth_manager.cancel(query.from_user.id)
    await state.clear()
    await query.answer("Отменено")
    await query.message.edit_text("❌ Добавление аккаунта отменено")


async def on_session_file(message: Message, bot, state: FSMContext) -> bool:
    if not message.document:
        return False
    fname = message.document.file_name or ""
    if not fname.endswith(".session"):
        return False

    session_name = fname[:-8]
    caption = (message.caption or "").strip().split()
    if len(caption) < 3:
        await message.answer(
            "❌ Подпись к .session файлу:\n"
            "<code>acc1 API_ID API_HASH [socks5://...]</code>",
        )
        return True

    name, api_id_raw, api_hash = caption[0], caption[1], caption[2]
    proxy = caption[3] if len(caption) > 3 else None

    file = await bot.get_file(message.document.file_id)
    buffer = await bot.download_file(file.file_path)
    Path(f"{session_name}.session").write_bytes(buffer.read())

    add_account(
        name,
        session_name,
        api_id=int(api_id_raw),
        api_hash=api_hash,
        proxy=proxy if proxy and proxy != "-" else None,
    )
    await message.answer(
        f"✅ <b>Session загружен</b>\n"
        f"{SEP}\n"
        f"👤 <b>{html.escape(name)}</b>\n"
        f"📱 <code>{html.escape(session_name)}</code>",
    )
    return True
