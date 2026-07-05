from dataclasses import dataclass
from urllib.parse import urlparse

import socks


@dataclass(frozen=True)
class Socks5Proxy:
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def as_telethon_tuple(self) -> tuple:
        if self.username:
            return (
                socks.SOCKS5,
                self.host,
                self.port,
                True,
                self.username,
                self.password or "",
            )
        return (socks.SOCKS5, self.host, self.port)

    def label(self) -> str:
        auth = f"{self.username}@" if self.username else ""
        return f"socks5://{auth}{self.host}:{self.port}"


def _from_url(url: str) -> Socks5Proxy:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"socks5", "socks5h"}:
        raise ValueError(f"Поддерживается только SOCKS5, получено: {scheme or url}")

    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        raise ValueError(f"Некорректный SOCKS5 URL: {url}")

    return Socks5Proxy(
        host=host,
        port=int(port),
        username=parsed.username or None,
        password=parsed.password or None,
    )


def _from_host_port(raw: str) -> Socks5Proxy:
    raw = raw.strip()
    if "@" in raw and "://" not in raw:
        auth, hostport = raw.rsplit("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)
        else:
            username, password = auth, None
        host, port_str = hostport.rsplit(":", 1)
        return Socks5Proxy(host=host, port=int(port_str), username=username, password=password)

    if raw.startswith("socks5://") or raw.startswith("socks5h://"):
        return _from_url(raw)

    host, port_str = raw.rsplit(":", 1)
    return Socks5Proxy(host=host.strip(), port=int(port_str.strip()))


def parse_socks5_proxy(raw: str | dict | None, *, account_name: str) -> Socks5Proxy | None:
    if raw is None or raw == "":
        return None

    if isinstance(raw, dict):
        host = str(raw.get("host", "")).strip()
        port = raw.get("port")
        if not host or port is None:
            raise ValueError(f"Аккаунт '{account_name}': proxy.host и proxy.port обязательны")
        return Socks5Proxy(
            host=host,
            port=int(port),
            username=(str(raw.get("username")).strip() if raw.get("username") else None) or None,
            password=(str(raw.get("password")).strip() if raw.get("password") else None) or None,
        )

    text = str(raw).strip()
    if not text:
        return None

    try:
        return _from_host_port(text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Аккаунт '{account_name}': неверный SOCKS5 прокси — {exc}") from exc


def validate_proxy_required(accounts: tuple, min_accounts: int = 2) -> None:
    enabled = [account for account in accounts if account.enabled]
    if len(enabled) < min_accounts:
        return

    without_proxy = [account.name for account in enabled if account.proxy is None]
    if len(without_proxy) > 1:
        raise RuntimeError(
            f"Без прокси может быть только 1 аккаунт. Сейчас без прокси: {', '.join(without_proxy)}"
        )

    missing = [account.name for account in enabled if account.proxy is None]
    with_proxy = [account for account in enabled if account.proxy is not None]

    # 2+ аккаунтов: ровно один может быть без прокси, остальным прокси обязателен
    if len(enabled) >= 2 and len(with_proxy) < len(enabled) - 1:
        raise RuntimeError(
            f"При {len(enabled)} аккаунтах максимум один без прокси. "
            f"Добавьте SOCKS5: {', '.join(missing)}"
        )

    endpoints = [(account.proxy.host, account.proxy.port) for account in with_proxy]
    if len(endpoints) != len(set(endpoints)):
        raise RuntimeError(
            "Каждый аккаунт с прокси должен иметь уникальный host:port"
        )
