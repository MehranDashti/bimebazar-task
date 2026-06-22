from abc import ABC, abstractmethod


class ProviderError(Exception):
    pass


class CapabilityNotSupported(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class InsufficientProviderStock(ProviderError):
    pass


class BaseProviderAdapter(ABC):
    @abstractmethod
    async def check_stock(self, sku: str) -> int: ...

    async def hold_stock(self, sku: str, qty: int, reservation_id: int) -> str | None:
        raise CapabilityNotSupported(
            f"{self.__class__.__name__} does not support hold_stock"
        )

    async def release_hold(self, hold_ref: str) -> bool:
        raise CapabilityNotSupported(
            f"{self.__class__.__name__} does not support release_hold"
        )

    async def confirm_hold(self, hold_ref: str) -> bool:
        raise CapabilityNotSupported(
            f"{self.__class__.__name__} does not support confirm_hold"
        )
