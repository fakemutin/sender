import logging
from dataclasses import dataclass, field

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from proxy import parse_socks5_proxy

logger = logging.getLogger(__name__)


@dataclass
class PendingAuth:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    name: str
    session_name: str
    api_id: int
    api_hash: str
    proxy_raw: str | None = None
    code: str = ""


class AccountAuthManager:
    def __init__(self) -> None:
        self._pending: dict[int, PendingAuth] = {}

    def get(self, admin_id: int) -> PendingAuth | None:
        return self._pending.get(admin_id)

    async def cancel(self, admin_id: int) -> None:
        pending = self._pending.pop(admin_id, None)
        if pending and pending.client.is_connected():
            await pending.client.disconnect()

    async def cancel_all(self) -> None:
        for admin_id in list(self._pending):
            await self.cancel(admin_id)

    def _build_client(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        proxy_raw: str | None,
        account_name: str,
    ) -> TelegramClient:
        kwargs: dict = {}
        if proxy_raw and proxy_raw.strip() not in ("-", "нет", "no", ""):
            proxy = parse_socks5_proxy(proxy_raw.strip(), account_name=account_name)
            kwargs["proxy"] = proxy.as_telethon_tuple()
        return TelegramClient(session_name, api_id, api_hash, **kwargs)

    async def start(
        self,
        admin_id: int,
        *,
        name: str,
        phone: str,
        api_id: int,
        api_hash: str,
        proxy_raw: str | None = None,
    ) -> None:
        await self.cancel(admin_id)
        session_name = phone.strip()
        client = self._build_client(session_name, api_id, api_hash, proxy_raw, name)
        await client.connect()

        if await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Аккаунт уже авторизован — .session уже есть")

        sent = await client.send_code_request(session_name)
        self._pending[admin_id] = PendingAuth(
            client=client,
            phone=session_name,
            phone_code_hash=sent.phone_code_hash,
            name=name,
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            proxy_raw=proxy_raw,
        )

    async def submit_code(self, admin_id: int, code: str) -> str:
        pending = self._pending.get(admin_id)
        if not pending:
            raise RuntimeError("Нет активной авторизации — /addaccount")

        try:
            await pending.client.sign_in(
                pending.phone,
                code,
                phone_code_hash=pending.phone_code_hash,
            )
        except SessionPasswordNeededError:
            return "password"

        if pending.client.is_connected():
            await pending.client.disconnect()
        self._pending.pop(admin_id, None)
        return "ok"

    async def submit_password(self, admin_id: int, password: str) -> None:
        pending = self._pending.get(admin_id)
        if not pending:
            raise RuntimeError("Нет активной авторизации")
        await pending.client.sign_in(password=password)
        if pending.client.is_connected():
            await pending.client.disconnect()
        self._pending.pop(admin_id, None)


auth_manager = AccountAuthManager()
