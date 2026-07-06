import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proxy import parse_socks5_proxy
from text_utils import proxy_to_string


@dataclass
class ParsedAccount:
    phone: str
    api_id: int
    api_hash: str
    proxy: str | None = None
    session_file: str | None = None
    twofa: str | None = None


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        raise ValueError("номер телефона не найден")
    return f"+{digits}"


def _parse_proxy_value(raw: Any, account_name: str = "import") -> str | None:
    if raw is None or raw == "" or raw is False:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text in ("-", "none", "null"):
            return None
        proxy = parse_socks5_proxy(text, account_name=account_name)
        return proxy_to_string(proxy)
    if isinstance(raw, dict):
        proxy = parse_socks5_proxy(raw, account_name=account_name)
        return proxy_to_string(proxy)
    if isinstance(raw, list) and len(raw) >= 3:
        # [type, host, port, rdns?, user?, pass?] — Telethon / seller formats
        host = str(raw[1])
        port = int(raw[2])
        username = str(raw[4]) if len(raw) > 4 and raw[4] else None
        password = str(raw[5]) if len(raw) > 5 and raw[5] else None
        proxy = parse_socks5_proxy(
            {"host": host, "port": port, "username": username, "password": password},
            account_name=account_name,
        )
        return proxy_to_string(proxy)
    return None


def parse_account_json(
    text: str,
    *,
    account_name: str = "import",
    filename: str | None = None,
) -> ParsedAccount:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON должен быть объектом")

    api_id = data.get("api_id") or data.get("app_id") or data.get("apiId")
    api_hash = data.get("api_hash") or data.get("app_hash") or data.get("apiHash")
    if not api_id or not api_hash:
        raise ValueError("В JSON нужны api_id/app_id и api_hash/app_hash")

    phone_raw = (
        data.get("phone")
        or data.get("session_file")
        or data.get("session")
        or data.get("number")
    )

    session_hint = None
    if filename:
        stem = Path(filename).stem  # 244424904_f560
        session_hint = stem.split("_")[0] if stem else None

    if not phone_raw and session_hint:
        phone_raw = session_hint

    if not phone_raw:
        raise ValueError("В JSON нет phone — укажите в файле или назовите json как номер.session")

    phone = _normalize_phone(str(phone_raw))
    session_file = data.get("session_file") or session_hint or phone
    if session_file and str(session_file).strip():
        session_name = _normalize_phone(str(session_file)) if re.sub(r"\D", "", str(session_file)) else str(session_file)
    else:
        session_name = phone

    proxy = _parse_proxy_value(
        data.get("proxy") or data.get("socks5") or data.get("proxy_str"),
        account_name=account_name,
    )
    twofa = data.get("twoFA") or data.get("2fa") or data.get("password") or data.get("twofa")

    return ParsedAccount(
        phone=phone,
        api_id=int(api_id),
        api_hash=str(api_hash).strip(),
        proxy=proxy,
        session_file=session_name,
        twofa=str(twofa).strip() if twofa else None,
    )


def session_name_from_filename(filename: str) -> str:
    name = Path(filename).name
    if name.endswith(".session"):
        name = name[:-8]
    name = name.strip()
    if name and not name.startswith("+"):
        if name.isdigit():
            name = f"+{name}"
    return _normalize_phone(name) if re.sub(r"\D", "", name) else name


def parse_caption(caption: str | None) -> tuple[str | None, str | None]:
    """caption: acc1  или  acc1 socks5://..."""
    if not caption:
        return None, None
    parts = caption.strip().split(maxsplit=1)
    acc_name = parts[0] if parts else None
    proxy = parts[1].strip() if len(parts) > 1 else None
    if proxy in ("-", "none", "нет"):
        proxy = None
    return acc_name, proxy


def pending_key(phone: str) -> str:
    return _normalize_phone(phone)


def format_import_status(pending: dict) -> str:
    lines = [
        f"👤 Имя: <b>{pending.get('name', '—')}</b>",
        f"📱 <code>{pending.get('phone', '—')}</code>",
        f"🔑 api_id: <b>{pending.get('api_id', '—')}</b>",
        f"🧦 Прокси: <code>{pending.get('proxy') or 'нет'}</code>",
        f"📄 JSON: {'✅' if pending.get('has_json') else '❌'}",
        f"💾 Session: {'✅' if pending.get('has_session') else '❌'}",
    ]
    return "\n".join(lines)
