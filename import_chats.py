from pathlib import Path

from storage import append_allowed_chats, append_addlists, load_accounts_raw
from text_utils import parse_chat_text


def import_from_text(text: str, target: str | None = None) -> dict:
    parsed = parse_chat_text(text)
    chats_added = 0
    addlists_added = 0

    if parsed["chats"]:
        chats_added = append_allowed_chats(target, parsed["chats"])
    if parsed["addlists"]:
        addlists_added = append_addlists(target, parsed["addlists"])

    payload = load_accounts_raw()
    if target:
        account = next(
            (item for item in payload.get("accounts", []) if item.get("name") == target),
            None,
        )
        scope = account or {}
    else:
        scope = payload.get("defaults", {})

    allowed = scope.get("allowed_chats") or []
    addlists = scope.get("addlists") or []
    if isinstance(allowed, str):
        allowed = [part.strip() for part in allowed.split(",") if part.strip()]
    if isinstance(addlists, str):
        addlists = [part.strip() for part in addlists.split(",") if part.strip()]

    return {
        "raw_urls": parsed["raw_urls"],
        "new_chats": chats_added,
        "new_addlists": addlists_added,
        "total_chats": len(allowed),
        "total_addlists": len(addlists),
        "target": target or "defaults",
    }


def import_from_file(path: Path, target: str | None = None) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    result = import_from_text(text, target=target)
    result["file"] = str(path)
    return result
