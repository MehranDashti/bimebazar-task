import httpx

from app.models.inventory_provider import InventoryProvider
from app.providers.base import (
    BaseProviderAdapter,
    CapabilityNotSupported,
    InsufficientProviderStock,
    ProviderTimeout,
    ProviderUnavailable,
)


class ExternalHttpProviderAdapter(BaseProviderAdapter):
    """
    Calls an external REST API. Expected endpoint conventions:
      GET  {base_url}/stock/{sku}             -> {"qty": int}
      POST {base_url}/holds                   -> {"hold_ref": str}
      DELETE {base_url}/holds/{hold_ref}      -> 204
      POST {base_url}/holds/{hold_ref}/confirm -> 200
    """

    def __init__(self, provider: InventoryProvider) -> None:
        self._provider = provider
        self._capabilities: dict = provider.capabilities or {}
        self._base_url = (provider.base_url or "").rstrip("/")
        self._timeout = provider.timeout_seconds
        self._headers = self._build_auth_headers(provider.auth_config or {})

    def _build_auth_headers(self, auth_config: dict) -> dict:
        auth_type = auth_config.get("type")
        if auth_type == "api_key":
            return {auth_config["header"]: auth_config["value"]}
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {auth_config['token']}"}
        return {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(self._timeout),
            trust_env=False,  # ignore system proxy env vars
        )

    def _require_capability(self, cap: str) -> None:
        if not self._capabilities.get(cap):
            raise CapabilityNotSupported(
                f"Provider '{self._provider.name}' does not support '{cap}'"
            )

    async def check_stock(self, sku: str) -> int:
        try:
            async with self._client() as client:
                resp = await client.get(f"{self._base_url}/stock/{sku}")
                resp.raise_for_status()
                return int(resp.json()["qty"])
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"check_stock timed out for sku={sku}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(str(exc)) from exc

    async def hold_stock(self, sku: str, qty: int, reservation_id: int) -> str | None:
        self._require_capability("hold_stock")
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url}/holds",
                    json={"sku": sku, "qty": qty, "reservation_id": reservation_id},
                )
                if resp.status_code == 409:
                    raise InsufficientProviderStock(
                        resp.json().get("detail", "Insufficient stock at provider")
                    )
                resp.raise_for_status()
                return resp.json().get("hold_ref")
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"hold_stock timed out for sku={sku}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(str(exc)) from exc

    async def release_hold(self, hold_ref: str) -> bool:
        self._require_capability("release_hold")
        try:
            async with self._client() as client:
                resp = await client.delete(f"{self._base_url}/holds/{hold_ref}")
                return resp.status_code in (200, 204)
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            return False  # release failure is non-fatal

    async def confirm_hold(self, hold_ref: str) -> bool:
        self._require_capability("confirm_hold")
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url}/holds/{hold_ref}/confirm"
                )
                resp.raise_for_status()
                return True
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                f"confirm_hold timed out for hold_ref={hold_ref}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(str(exc)) from exc
