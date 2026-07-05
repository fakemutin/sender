import re

from proxy import Socks5Proxy

_URL_RE = re.compile(r"https?://t\.me/[^\s\)\]<>\"']+", re.I)


def proxy_to_string(proxy: Socks5Proxy) -> str:
    if proxy.username:
        password = proxy.password or ""
        return f"socks5://{proxy.username}:{password}@{proxy.host}:{proxy.port}"
    return f"socks5://{proxy.host}:{proxy.port}"


def mask_proxy_string(raw: str) -> str:
    if "@" in raw:
        return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", raw)
    return raw


def _normalize_tme_url(url: str) -> tuple[str, str] | None:
    url = url.strip().rstrip(".,;")
    url = url.replace("http://", "https://")
    if not url.lower().startswith("https://t.me/"):
        return None

    path = url[len("https://t.me/") :].split("?")[0].strip("/")
    if not path:
        return None

    parts = path.split("/")
    head = parts[0].lower()

    if head == "addlist" and len(parts) > 1:
        return ("addlist", parts[1].lower())
    if head == "joinchat" and len(parts) > 1:
        return ("chat", f"joinchat/{parts[1]}")
    if head.startswith("+"):
        return ("chat", head)
    if head == "c" and len(parts) > 1:
        return ("chat", f"c/{parts[1]}")

    username = parts[0].lower().lstrip("@")
    if username:
        return ("chat", username)
    return None


def parse_chat_text(text: str) -> dict:
    chats: list[str] = []
    addlists: list[str] = []
    seen_chats: set[str] = set()
    seen_addlists: set[str] = set()

    for raw_url in _URL_RE.findall(text):
        parsed = _normalize_tme_url(raw_url)
        if not parsed:
            continue
        kind, token = parsed
        if kind == "addlist":
            if token not in seen_addlists:
                seen_addlists.add(token)
                addlists.append(token)
        elif token not in seen_chats:
            seen_chats.add(token)
            chats.append(token)

    for match in re.finditer(r"(?<![/\w])@([A-Za-z0-9_]{3,})", text):
        token = match.group(1).lower()
        if token not in seen_chats:
            seen_chats.add(token)
            chats.append(token)

    return {
        "chats": chats,
        "addlists": addlists,
        "raw_urls": len(_URL_RE.findall(text)),
    }


def extract_chat_tokens(text: str) -> list[str]:
    return parse_chat_text(text)["chats"]


def extract_addlist_slugs(text: str) -> list[str]:
    return parse_chat_text(text)["addlists"]
