import html
import re

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from account_auth import auth_manager
from flow_state import clear_flow, flow_data, get_flow, set_flow
from roman_keypad import code_display, roman_keypad
from storage import add_account

SEP = "────────────────────"


def _back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="auth_cancel")]]
    )


async def start_add_account(message: Message, user_id: int) -> None:
    clear_flow(user_id)
    set_flow(user_id, "name", {})
    await message.answer(
        "➕ <b>Добавление аккаунта</b>\n"
        f"{SEP}\n"
        "Шаг 1/5 — имя аккаунта\n"
        "Пример: <code>acc2</code>",
        reply_markup=_back(),
    )


async def handle_flow_text(message: Message, user_id: int) -> bool:
    step = get_flow(user_id)
    if not step:
        return False

    current = step["step"]
    text = (message.text or "").strip()

    if current == "name":
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", text):
            await message.answer("❌ Имя: латиница, цифры, _- (2–32 символа)")
            return True
        set_flow(user_id, "phone", {"name": text})
        await message.answer(
            f"✅ Имя: <b>{html.escape(text)}</b>\n\n"
            "Шаг 2/5 — номер телефона\n"
            "Пример: <code>+79001234567</code>",
            reply_markup=_back(),
        )
        return True

    if current == "phone":
        phone = text.replace(" ", "")
        if not re.fullmatch(r"\+\d{10,15}", phone):
            await message.answer("❌ Формат: <code>+79001234567</code>")
            return True
        set_flow(user_id, "api_id", {"phone": phone})
        await message.answer("Шаг 3/5 — <b>api_id</b>\n(my.telegram.org)", reply_markup=_back())
        return True

    if current == "api_id":
        try:
            api_id = int(text)
        except ValueError:
            await message.answer("❌ api_id — число")
            return True
        set_flow(user_id, "api_hash", {"api_id": api_id})
        await message.answer("Шаг 4/5 — <b>api_hash</b>", reply_markup=_back())
        return True

    if current == "api_hash":
        if len(text) < 16:
            await message.answer("❌ api_hash слишком короткий")
            return True
        set_flow(user_id, "proxy", {"api_hash": text})
        await message.answer(
            "Шаг 5/5 — SOCKS5 прокси\n"
            "<code>socks5://user:pass@host:1080</code>\n"
            "или <code>-</code> без прокси",
            reply_markup=_back(),
        )
        return True

    if current == "proxy":
        data = flow_data(user_id)
        proxy_raw = text
        wait = await message.answer("📨 Отправляю код в Telegram...")
        try:
            await auth_manager.start(
                user_id,
                name=data["name"],
                phone=data["phone"],
                api_id=data["api_id"],
                api_hash=data["api_hash"],
                proxy_raw=proxy_raw if proxy_raw != "-" else None,
            )
        except Exception as exc:
            await wait.edit_text(f"❌ {html.escape(str(exc))}")
            clear_flow(user_id)
            return True

        pending = auth_manager.get(user_id)
        if pending:
            pending.proxy_raw = proxy_raw if proxy_raw != "-" else None

        set_flow(user_id, "code", {"proxy_raw": proxy_raw if proxy_raw != "-" else None})
        await wait.edit_text(
            "🔐 <b>Код из Telegram</b>\n"
            f"{SEP}\n"
            f"📱 <code>{html.escape(data['phone'])}</code>\n"
            f"Код: {code_display('')}\n\n"
            "<i>Нажимайте римские цифры 👇</i>",
            reply_markup=roman_keypad(""),
        )
        return True

    if current == "password":
        try:
            await auth_manager.submit_password(user_id, text)
        except Exception as exc:
            await message.answer(f"❌ {html.escape(str(exc))}")
            return True
        data = flow_data(user_id)
        add_account(
            data["name"],
            data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy=data.get("proxy_raw"),
        )
        clear_flow(user_id)
        await message.answer(
            f"✅ <b>Аккаунт добавлен</b>\n"
            f"{SEP}\n"
            f"👤 <b>{html.escape(data['name'])}</b>\n"
            f"📱 <code>{html.escape(data['phone'])}</code>",
        )
        return True

    return False


async def on_auth_digit(query: CallbackQuery, user_id: int) -> None:
    flow = get_flow(user_id)
    if not flow or flow.get("step") != "code":
        await query.answer("Сначала /addaccount", show_alert=True)
        return

    pending = auth_manager.get(user_id)
    if not pending:
        await query.answer("Сессия истекла — /addaccount", show_alert=True)
        clear_flow(user_id)
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
            result = await auth_manager.submit_code(user_id, pending.code)
        except Exception as exc:
            await query.message.edit_text(f"❌ {html.escape(str(exc))}")
            clear_flow(user_id)
            return

        data = flow_data(user_id)
        if result == "password":
            set_flow(user_id, "password", {})
            await query.message.edit_text(
                "🔒 <b>2FA пароль</b>\n"
                f"{SEP}\n"
                "Отправьте пароль двухфакторной авторизации:",
            )
            return

        add_account(
            data["name"],
            data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy=data.get("proxy_raw"),
        )
        clear_flow(user_id)
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
    data = flow_data(user_id)
    await query.message.edit_text(
        "🔐 <b>Код из Telegram</b>\n"
        f"{SEP}\n"
        f"📱 <code>{html.escape(data.get('phone', ''))}</code>\n"
        f"Код: {code_display(pending.code)}\n\n"
        "<i>Нажимайте римские цифры 👇</i>",
        reply_markup=roman_keypad(pending.code),
    )


async def on_auth_cancel(query: CallbackQuery, user_id: int) -> None:
    from storage import clear_pending_import

    await auth_manager.cancel(user_id)
    clear_flow(user_id)
    clear_pending_import(user_id)
    await query.answer("Отменено")
    await query.message.edit_text("❌ Отменено")

