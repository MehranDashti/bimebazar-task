from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.inventory_provider import InventoryProvider
    from app.models.product import Product
    from app.models.reservation import Reservation


class ProviderItemStatus(str, PyEnum):
    pending = "pending"
    held = "held"
    provider_failed = "provider_failed"
    released = "released"
    confirmed = "confirmed"


class ReservationItem(Base):
    __tablename__ = "reservation_items"
    __table_args__ = (Index("idx_ri_reservation", "reservation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    inventory_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory.id"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_providers.id"), nullable=False
    )
    qty_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_hold_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_status: Mapped[ProviderItemStatus] = mapped_column(
        Enum(ProviderItemStatus), nullable=False, default=ProviderItemStatus.pending
    )
    provider_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    reservation: Mapped["Reservation"] = relationship(  # noqa: F821
        "Reservation", back_populates="items"
    )
    product: Mapped["Product"] = relationship("Product", lazy="selectin")  # noqa: F821
    provider: Mapped["InventoryProvider"] = relationship(  # noqa: F821
        "InventoryProvider", lazy="selectin"
    )
