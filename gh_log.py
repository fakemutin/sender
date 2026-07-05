import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOG_FILE = Path(os.getenv("GH_LOG_FILE", "gh_log.json"))
MAX_ENTRIES = int(os.getenv("GH_LOG_MAX", "100"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> deque:
    if not LOG_FILE.exists():
        return deque(maxlen=MAX_ENTRIES)
    try:
        with LOG_FILE.open(encoding="utf-8") as handle:
            items = json.load(handle)
        return deque(items[-MAX_ENTRIES:], maxlen=MAX_ENTRIES)
    except (json.JSONDecodeError, OSError):
        return deque(maxlen=MAX_ENTRIES)


def _save(entries: deque) -> None:
    with LOG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(list(entries), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def log_event(
    *,
    chat_id: int,
    chat_label: str,
    action: str,
    detail: str,
    account: str = "",
    ok: bool = True,
) -> None:
    entries = _load()
    entries.append(
        {
            "at": _now(),
            "chat_id": chat_id,
            "chat": chat_label,
            "action": action,
            "detail": detail,
            "account": account,
            "ok": ok,
        }
    )
    _save(entries)


def recent(limit: int = 15) -> list[dict]:
    entries = _load()
    return list(entries)[-limit:]


def format_recent(limit: int = 15) -> str:
    items = recent(limit)
    if not items:
        return "Пока нет записей Group Help"
    lines = []
    for item in reversed(items):
        icon = "✅" if item.get("ok", True) else "❌"
        acc = f" [{item['account']}]" if item.get("account") else ""
        lines.append(
            f"{icon} {item.get('at', '?')}{acc}\n"
            f"   {item.get('chat', '?')} — {item.get('action')}: {item.get('detail')}"
        )
    return "\n\n".join(lines)
