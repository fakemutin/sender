#!/usr/bin/env python3
"""Count unique Telegram chats and addlist folders from pasted list."""
import re
import sys
from pathlib import Path


def normalize(url: str) -> str | None:
    url = url.strip().rstrip(".,;")
    url = url.replace("http://", "https://")
    if not url.startswith("https://t.me/"):
        return None
    path = url[len("https://t.me/") :].split("?")[0].rstrip("/")
    parts = path.split("/")
    if not parts or not parts[0]:
        return None
    if parts[0] == "addlist":
        return f"https://t.me/addlist/{parts[1]}" if len(parts) > 1 else None
    if parts[0] == "joinchat" and len(parts) > 1:
        return f"https://t.me/joinchat/{parts[1]}"
    if parts[0].startswith("+"):
        return f"https://t.me/{parts[0]}"
    if parts[0] == "c" and len(parts) > 1:
        return f"https://t.me/c/{parts[1]}"
    # username with optional message id
    return f"https://t.me/{parts[0].lower()}"


def analyze(text: str) -> dict:
    raw = re.findall(r"https?://t\.me/[^\s\)\]<>\"']+", text, flags=re.I)
    folders: set[str] = set()
    chats: set[str] = set()
    for item in raw:
        norm = normalize(item)
        if not norm:
            continue
        if "/addlist/" in norm:
            folders.add(norm.lower())
        else:
            chats.add(norm.lower())

    return {
        "raw_total": len(raw),
        "folders_unique": len(folders),
        "chats_unique": len(chats),
        "total_unique": len(folders) + len(chats),
        "folders": folders,
        "chats": chats,
    }


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/user_paste.txt")
    text = path.read_text(encoding="utf-8")
    r = analyze(text)
    print(f"Всего URL в тексте: {r['raw_total']}")
    print(f"Уникальных папок (addlist): {r['folders_unique']}")
    print(f"Уникальных чатов: {r['chats_unique']}")
    print(f"Всего уникальных записей: {r['total_unique']}")
    print(f"Дубликатов URL: {r['raw_total'] - r['total_unique']}")


if __name__ == "__main__":
    main()
