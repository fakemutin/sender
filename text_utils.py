import re

from proxy import Socks5Proxy


def proxy_to_string(proxy: Socks5Proxy) -> str:
    if proxy.username:
        password = proxy.password or ""
        return f"socks5://{proxy.username}:{password}@{proxy.host}:{proxy.port}"
    return f"socks5://{proxy.host}:{proxy.port}"


def mask_proxy_string(raw: str) -> str:
    if "@" in raw:
        return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", raw)
    return raw


def extract_chat_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r"https?://t\.me/([A-Za-z0-9_+\-/]+)", text, flags=re.I):
        path = match.group(1).strip("/")
        if path.lower().startswith("addlist/"):
            continue
        token = path.split("/")[0].lower().lstrip("@")
        if token.startswith("+") or token.startswith("joinchat"):
            token = path.split("/")[0]
        if token and token not in seen:
            seen.add(token.lower())
            tokens.append(token)

    for match in re.finditer(r"(?<![/\w])@([A-Za-z0-9_]{3,})", text):
        token = match.group(1).lower()
        if token not in seen:
            seen.add(token)
            tokens.append(token)

    return tokens
