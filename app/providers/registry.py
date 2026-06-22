from app.models.inventory import Inventory
from app.models.inventory_provider import InventoryProvider, ProviderType
from app.providers.base import BaseProviderAdapter
from app.providers.external_http import ExternalHttpProviderAdapter
from app.providers.internal import InternalProviderAdapter


class ProviderRegistry:
    @staticmethod
    def resolve(
        provider: InventoryProvider,
        inventory_row: Inventory | None = None,
    ) -> BaseProviderAdapter:
        if provider.type == ProviderType.internal:
            if inventory_row is None:
                raise ValueError("InternalProviderAdapter requires an inventory_row")
            return InternalProviderAdapter(inventory_row)
        return ExternalHttpProviderAdapter(provider)
