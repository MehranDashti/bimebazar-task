"""
Route-layer tests for reservations and payment-outcome.

Strategy: override get_reservation_service with a MagicMock so these tests
are pure HTTP-layer checks — no DB, no provider I/O.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_order_service, get_reservation_service
from app.core.exceptions import (
    DuplicateOrderError,
    InsufficientStockError,
    ReservationNotFound,
    ReservationStateError,
)
from app.models.order import OrderStatus
from app.models.reservation import ReservationStatus
from app.models.reservation_item import ProviderItemStatus
from main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _stub_reservation(reservation_id: int = 1, with_items: bool = True):
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=1, product_id=1, provider_id=1, provider_name="InternalStock",
        qty_requested=2,
        provider_status=ProviderItemStatus.held,
        provider_hold_ref=None,
        provider_error_message=None,
        provider=SimpleNamespace(name="InternalStock"),
    )
    return SimpleNamespace(
        id=reservation_id,
        user_id="usr_test",
        status=ReservationStatus.pending,
        expires_at=now + timedelta(minutes=15),
        created_at=now,
        items=[item] if with_items else [],
    )


def _stub_order(order_id: int = 1, reservation_id: int = 1):
    return SimpleNamespace(
        id=order_id,
        reservation_id=reservation_id,
        user_id="usr_test",
        status=OrderStatus.created,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_svc():
    svc = AsyncMock()
    svc.create = AsyncMock(return_value=_stub_reservation())
    svc.get_with_items = AsyncMock(return_value=_stub_reservation())
    svc.confirm = AsyncMock(return_value=_stub_order())
    svc.cancel = AsyncMock(return_value=None)
    return svc


@pytest.fixture(autouse=True)
def override_reservation_svc(mock_svc):
    app.dependency_overrides[get_reservation_service] = lambda: mock_svc
    yield
    app.dependency_overrides.pop(get_reservation_service, None)


# ── POST /reservations ────────────────────────────────────────────────────────

async def test_create_reservation_returns_201(client: AsyncClient):
    resp = await client.post(
        "/api/v1/reservations",
        json={"user_id": "usr_test", "items": [{"product_id": 1, "qty": 2}]},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["id"] == 1
    assert data["status"] == "pending"
    assert isinstance(data["items"], list)


async def test_create_reservation_insufficient_stock_returns_409(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.create.side_effect = InsufficientStockError("not enough")
    resp = await client.post(
        "/api/v1/reservations",
        json={"user_id": "usr_test", "items": [{"product_id": 1, "qty": 99}]},
    )
    assert resp.status_code == 409


async def test_create_reservation_duplicate_product_ids_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "user_id": "usr_test",
            "items": [
                {"product_id": 1, "qty": 2},
                {"product_id": 1, "qty": 3},
            ],
        },
    )
    assert resp.status_code == 422


async def test_create_reservation_missing_user_id_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/reservations",
        json={"items": [{"product_id": 1, "qty": 2}]},
    )
    assert resp.status_code == 422


async def test_create_reservation_empty_items_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/reservations",
        json={"user_id": "usr_test", "items": []},
    )
    assert resp.status_code == 422


# ── GET /reservations/{id} ────────────────────────────────────────────────────

async def test_get_reservation_returns_200(client: AsyncClient):
    resp = await client.get("/api/v1/reservations/1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == 1


async def test_get_reservation_not_found_returns_404(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.get_with_items.side_effect = ReservationNotFound("not found")
    resp = await client.get("/api/v1/reservations/9999")
    assert resp.status_code == 404


# ── POST /reservations/{id}/confirm ──────────────────────────────────────────

async def test_confirm_reservation_returns_200(client: AsyncClient):
    resp = await client.post("/api/v1/reservations/1/confirm")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reservation_id"] == 1
    assert data["status"] == "created"


async def test_confirm_reservation_not_found_returns_404(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.confirm.side_effect = ReservationNotFound("not found")
    resp = await client.post("/api/v1/reservations/9999/confirm")
    assert resp.status_code == 404


async def test_confirm_reservation_state_error_returns_422(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.confirm.side_effect = ReservationStateError("already confirmed")
    resp = await client.post("/api/v1/reservations/1/confirm")
    assert resp.status_code == 422


# ── POST /reservations/{id}/cancel ───────────────────────────────────────────

async def test_cancel_reservation_returns_204(client: AsyncClient):
    resp = await client.post("/api/v1/reservations/1/cancel")
    assert resp.status_code == 204


async def test_cancel_reservation_not_found_returns_404(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.cancel.side_effect = ReservationNotFound("not found")
    resp = await client.post("/api/v1/reservations/9999/cancel")
    assert resp.status_code == 404


# ── POST /payment-outcome ─────────────────────────────────────────────────────

async def test_payment_outcome_success_confirms_reservation(
    client: AsyncClient, mock_svc: AsyncMock
):
    resp = await client.post(
        "/api/v1/payment-outcome",
        json={"reservation_id": 1, "outcome": "success"},
    )
    assert resp.status_code == 200
    mock_svc.confirm.assert_awaited_once_with(1)


async def test_payment_outcome_failed_cancels_reservation(
    client: AsyncClient, mock_svc: AsyncMock
):
    resp = await client.post(
        "/api/v1/payment-outcome",
        json={"reservation_id": 1, "outcome": "failed"},
    )
    assert resp.status_code == 200
    mock_svc.cancel.assert_awaited_once_with(1)
    data = resp.json()["data"]
    assert data["status"] == "cancelled"


async def test_payment_outcome_duplicate_order_returns_409(
    client: AsyncClient, mock_svc: AsyncMock
):
    mock_svc.confirm.side_effect = DuplicateOrderError("already exists")
    resp = await client.post(
        "/api/v1/payment-outcome",
        json={"reservation_id": 1, "outcome": "success"},
    )
    assert resp.status_code == 409


async def test_payment_outcome_invalid_outcome_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/payment-outcome",
        json={"reservation_id": 1, "outcome": "pending"},
    )
    assert resp.status_code == 422
