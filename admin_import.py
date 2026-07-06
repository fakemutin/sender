import html
from pathlib import Path

from aiogram.types import Message

from account_import import (
    format_import_status,
    parse_account_json,
    parse_caption,
    pending_key,
    session_name_from_filename,
)
from flow_state import clear_flow
from storage import (
    clear_pending_import,
    get_pending_import,
    next_account_name,
    set_pending_import,
    upsert_account,
)

SEP = "────────────────────"


async def _verify_session(session_name: str, api_id: int, api_hash: str) -> tuple[bool, str]:
    try:
        from telethon import TelegramClient

        client = TelegramClient(session_name, api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return False, "сессия не авторизована"
        me = await client.get_me()
        await client.disconnect()
        label = me.username or me.first_name or session_name
        return True, f"@{me.username}" if me.username else label
    except Exception as exc:
        return False, str(exc)


async def _finalize_import(user_id: int, pending: dict) -> tuple[bool, str]:
    if not pending.get("has_json") or not pending.get("has_session"):
        return False, "incomplete"

    session_name = pending["session_name"]
    action = upsert_account(
        pending["name"],
        session_name,
        api_id=pending["api_id"],
        api_hash=pending["api_hash"],
        proxy=pending.get("proxy"),
    )
    ok, detail = await _verify_session(session_name, pending["api_id"], pending["api_hash"])
    clear_pending_import(user_id)
    clear_flow(user_id)

    status = "обновлён" if action == "updated" else "добавлен"
    auth = f"🔐 {detail}" if ok else f"⚠️ {detail}"
    return True, (
        f"✅ <b>Аккаунт {status}</b>\n"
        f"{SEP}\n"
        f"👤 <b>{html.escape(pending['name'])}</b>\n"
        f"📱 <code>{html.escape(session_name)}</code>\n"
        f"🧦 <code>{html.escape(pending.get('proxy') or 'нет')}</code>\n"
        f"{auth}"
    )


async def handle_json_file(message: Message, bot, user_id: int, content: bytes) -> bool:
    acc_name, caption_proxy = parse_caption(message.caption)
    try:
        parsed = parse_account_json(content.decode("utf-8", errors="replace"), account_name=acc_name or "import")
    except Exception as exc:
        await message.answer(f"❌ JSON: {html.escape(str(exc))}")
        return True

    name = acc_name or next_account_name()
    proxy = caption_proxy or parsed.proxy
    session_name = parsed.session_file or parsed.phone

    pending = get_pending_import(user_id) or {}
    pending.update(
        {
            "name": name,
            "phone": parsed.phone,
            "session_name": session_name,
            "api_id": parsed.api_id,
            "api_hash": parsed.api_hash,
            "proxy": proxy,
            "has_json": True,
            "has_session": pending.get("has_session", False),
        }
    )
    set_pending_import(user_id, pending)

    if Path(f"{session_name}.session").exists():
        pending["has_session"] = True
        set_pending_import(user_id, pending)

    done, text = await _finalize_import(user_id, pending)
    if done:
        await message.answer(text)
        return True

    await message.answer(
        "📄 <b>JSON принят</b>\n"
        f"{SEP}\n"
        f"{format_import_status(pending)}\n\n"
        "Теперь отправь <b>.session</b> Telethon\n"
        f"<i>имя файла: <code>{html.escape(session_name)}.session</code></i>",
    )
    return True


async def handle_session_file(message: Message, bot, user_id: int, content: bytes, filename: str) -> bool:
    acc_name, caption_proxy = parse_caption(message.caption)
    session_name = session_name_from_filename(filename)
    target = Path(f"{session_name}.session")
    target.write_bytes(content)

    pending = get_pending_import(user_id) or {}
    if pending.get("phone") and pending_key(pending["phone"]) != pending_key(session_name):
        await message.answer(
            "⚠️ Номер session не совпадает с JSON\n"
            f"JSON: <code>{html.escape(pending.get('phone', ''))}</code>\n"
            f"Session: <code>{html.escape(session_name)}</code>\n\n"
            "Отправь правильный .session или новый JSON",
        )
        return True

    if not pending.get("has_json"):
        name = acc_name or next_account_name()
        pending = {
            "name": name,
            "phone": session_name,
            "session_name": session_name,
            "has_session": True,
            "has_json": False,
            "proxy": caption_proxy,
        }
        set_pending_import(user_id, pending)
        await message.answer(
            "💾 <b>Session сохранён</b>\n"
            f"{SEP}\n"
            f"📱 <code>{html.escape(session_name)}</code>\n\n"
            "Теперь отправь <b>.json</b> аккаунта\n"
            f"Подпись (опционально): <code>{html.escape(name)}</code> или <code>{html.escape(name)} socks5://...</code>",
        )
        return True

    pending["session_name"] = session_name
    pending["has_session"] = True
    if caption_proxy:
        pending["proxy"] = caption_proxy
    set_pending_import(user_id, pending)

    done, text = await _finalize_import(user_id, pending)
    if done:
        await message.answer(text)
        return True

    await message.answer(f"{format_import_status(pending)}")
    return True


async def on_account_document(message: Message, bot, user_id: int) -> bool:
    if not message.document:
        return False

    fname = (message.document.file_name or "").lower()
    file = await bot.get_file(message.document.file_id)
    buffer = await bot.download_file(file.file_path)
    content = buffer.read()

    if fname.endswith(".json"):
        return await handle_json_file(message, bot, user_id, content)
    if fname.endswith(".session"):
        return await handle_session_file(message, bot, user_id, content, message.document.file_name or "")
    return False


async def start_import_help(message: Message, user_id: int) -> None:
    clear_flow(user_id)
    clear_pending_import(user_id)
    await message.answer(
        "📦 <b>Импорт аккаунта</b>\n"
        f"{SEP}\n\n"
        "<b>Способ 1 — два файла</b>\n"
        "1. Отправь <b>.json</b> (подпись: <code>acc1</code>)\n"
        "2. Отправь <b>.session</b> Telethon\n\n"
        "<b>Способ 2 — json + прокси в подписи</b>\n"
        "<code>acc1 socks5://user:pass@1.2.3.4:1080</code>\n\n"
        "<b>Способ 3 — альбом</b>\n"
        "Выдели .json + .session и отправь одним сообщением\n"
        "Подпись: <code>acc2</code>\n\n"
        "<i>JSON: phone, api_id, api_hash, proxy</i>\n"
        "/cancel — отмена",
    )
