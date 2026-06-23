# Architecture — Inventory Reservation Service

## Overview

The Inventory Reservation Service is a FastAPI application that manages inventory reservations for an e-commerce checkout flow. It sits between the storefront and the inventory layer and coordinates with one or more inventory providers (internal or external).

---

## System Layers

```
Flutter / Browser / API Consumer
        │  HTTP REST
        ▼
FastAPI Application (ASGI, uvicorn)
  ├─ Routers:  /reservations, /payment-outcome, /orders, /inventory, /providers
  ├─ Service Layer:  ReservationService, InventoryService, OrderService
  ├─ Repository Layer:  InventoryRepository, ReservationRepository, OrderRepository
  ├─ Provider Adapters:  InternalProviderAdapter, ExternalHttpProviderAdapter
  └─ Background Worker:  APScheduler expiry sweep (AsyncIOScheduler)
        │
        ▼
MySQL 8  (persistence, row-level locking via SELECT FOR UPDATE)
        │
        ▼
External Provider APIs  (optional, HTTP REST, timeout-isolated)
```

---

## Data Model

### Core Tables

| Table | Purpose |
|---|---|
| `products` | Product catalogue (id, sku, name) |
| `inventory_providers` | Provider registry (internal / external, capabilities, auth) |
| `inventory` | Stock per product per provider (`qty_available`, `qty_reserved`) |
| `reservations` | Checkout sessions (status, TTL expiry) |
| `reservation_items` | Line items linking reservation → inventory → provider |
| `orders` | Confirmed purchase records (1-to-1 with reservation) |

### Key Constraints

- `UniqueConstraint("product_id", "provider_id")` on `inventory` — one row per (product, provider)
- `idx_reservations_status_expires` — composite index enabling fast expiry sweep queries
- `reservation_items.provider_hold_ref` — external reference returned by provider API

---

## Reservation Lifecycle

```
          create()
             │
    [Phase 1: pre-flight check — no lock]
    SELECT best inventory row (qty_available - qty_reserved ≥ requested)
             │  fail: InsufficientStockError → 409
             ▼
    [Phase 2: re-check under SELECT FOR UPDATE]
    Acquire row lock → re-read qty → validate again
             │  fail: InsufficientStockError → 409
             ▼
    qty_reserved += requested  (optimistic hold)
    INSERT Reservation (status=pending, expires_at=now+TTL)
    INSERT ReservationItem (status=pending)
             │
    [Phase 3: provider hold]
    Call adapter.hold_stock()
      ✓ success       → provider_status=held, hold_ref saved
      ✗ Timeout/503   → provider_status=provider_failed (fail-open)
      ✗ 409 conflict  → InsufficientProviderStock → rollback reservation
             │
             ▼  status=pending, expires_at in future
    ────────────────────────────────────
    Payment gateway processes payment
    ────────────────────────────────────
             │
      ┌──────┴──────┐
   success        failed
      │               │
  confirm()       cancel()
      │               │
  qty_available    qty_reserved
  -= qty            -= qty
  qty_reserved      status=cancelled
  -= qty            release_hold() (non-fatal)
  status=confirmed
  confirm_hold() (non-fatal)
  INSERT Order
             │
             ▼
      [Background: expiry sweep]
      SELECT ... WHERE status=pending AND expires_at < now()
      FOR UPDATE SKIP LOCKED   ← multi-replica safe
      → release items → status=expired
```

---

## Concurrency Design

### Oversell Prevention (Two-Phase Lock)

Race conditions between concurrent reservations for the same SKU are prevented by a two-step protocol:

1. **Pre-flight (no lock)** — fast rejection before touching the database locks. Filters out requests that obviously cannot be fulfilled.
2. **Re-check under `SELECT FOR UPDATE`** — row-level exclusive lock prevents another transaction from modifying `qty_reserved` between our read and write.

The two-step approach minimises lock contention: only requests that pass the pre-flight check acquire a lock. The re-check under lock guards against TOCTOU races.

### Multi-Replica Expiry Safety

The background expiry sweep uses `SELECT ... FOR UPDATE SKIP LOCKED`. Multiple application replicas can run the sweep concurrently — each replica processes a different batch of expired reservations without conflicts. Rows being processed by another replica are skipped rather than blocked.

### Idempotency

`cancel()` and `expire_batch()` are idempotent:

- `cancel()` returns silently if the reservation is already `cancelled` or `expired`
- `expire_batch()` can be retried safely; `SKIP LOCKED` prevents double-processing

---

## Provider Architecture

### Adapter Pattern

All provider interactions go through a common interface (`BaseProviderAdapter`):

```python
async def check_stock(sku: str) -> int
async def hold_stock(sku, qty, reservation_id) -> str | None  # returns hold_ref
async def release_hold(hold_ref) -> bool
async def confirm_hold(hold_ref) -> bool
```

### Provider Types

| Type | Class | Description |
|---|---|---|
| `internal` | `InternalProviderAdapter` | Operates directly on the `Inventory` DB row |
| `external` | `ExternalHttpProviderAdapter` | Calls REST API via `httpx.AsyncClient` |

### Fail-Open Design

External provider failures during `hold_stock` are isolated from the reservation:

| Exception | Behaviour |
|---|---|
| `ProviderTimeout` | Reservation created; item marked `provider_failed` |
| `ProviderUnavailable` (5xx) | Same as timeout |
| `InsufficientProviderStock` (409) | Reservation aborted (provider out of stock) |

`confirm_hold` and `release_hold` failures are always non-fatal — local inventory state is authoritative.

### Capability Negotiation

Each provider declares its capabilities in a JSON column. `_require_capability()` raises `CapabilityNotSupported` before making a network call, avoiding unnecessary timeouts for unsupported operations.

---

## API Endpoints

| Method | Path | Status Codes | Description |
|---|---|---|---|
| `POST` | `/api/v1/reservations` | 201, 409, 422 | Create reservation |
| `GET` | `/api/v1/reservations/{id}` | 200, 404 | Get reservation |
| `POST` | `/api/v1/reservations/{id}/confirm` | 200, 404, 422 | Confirm (post-payment) |
| `POST` | `/api/v1/reservations/{id}/cancel` | 204, 404 | Cancel |
| `POST` | `/api/v1/payment-outcome` | 200, 409, 422 | Payment webhook (confirm / cancel) |
| `GET` | `/api/v1/orders/{id}` | 200, 404 | Get order |
| `GET` | `/api/v1/inventory/{product_id}/availability` | 200, 404 | Check availability |
| `POST` | `/api/v1/providers/{provider_id}/sync` | 200, 404 | Sync from external provider |

---

## Background Worker

`APScheduler` (`AsyncIOScheduler`) runs the expiry sweep at a configurable interval (`EXPIRY_SWEEP_INTERVAL_SECONDS`, default 60s):

- `max_instances=1` — prevents overlapping runs within a single replica
- `coalesce=True` — skips accumulated missed firings on startup
- Graceful lifecycle: started on `lifespan` startup, stopped on shutdown

---

## Configuration

All configuration flows through `pydantic-settings` (`get_settings()`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | MySQL async DSN |
| `RESERVATION_TTL_MINUTES` | 15 | Pending reservation lifetime |
| `EXPIRY_SWEEP_INTERVAL_SECONDS` | 60 | Background sweep frequency |

---

## Technology Stack

| Concern | Choice |
|---|---|
| Web framework | FastAPI (async) |
| ORM | SQLAlchemy 2.x async |
| Database | MySQL 8 (aiomysql) |
| Migrations | Alembic |
| HTTP client | httpx (async) |
| Background jobs | APScheduler (AsyncIOScheduler) |
| Validation | Pydantic v2 |
| Testing | pytest-asyncio, respx |
