# Inventory Reservation Service

A production-grade inventory reservation system built with FastAPI, async SQLAlchemy, and MySQL. Implements a time-bounded, two-phase locking reservation flow with pluggable external inventory providers, background expiry sweeping, and a full test suite.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Data Model](#data-model)
- [API Reference](#api-reference)
- [Reservation Lifecycle](#reservation-lifecycle)
- [Provider System](#provider-system)
- [Concurrency Design](#concurrency-design)
- [Background Expiry Worker](#background-expiry-worker)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Database Migrations](#database-migrations)
- [Seed Data](#seed-data)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Scalability Notes](#scalability-notes)

---

## Overview

This service solves the classic e-commerce oversell problem: multiple concurrent buyers competing for the same limited stock. It solves it with:

- **Two-phase locking** — pre-flight check (unlocked, fast) followed by re-check under `SELECT FOR UPDATE` before mutating inventory.
- **Time-bounded reservations** — every reservation expires after a configurable TTL (default 15 min). Inventory is released automatically if payment never arrives.
- **Pluggable provider adapters** — inventory can be held at an internal (database-managed) stock or at any external warehouse API. Both adapters implement the same interface.
- **Fail-open on transient provider errors** — a provider timeout or 5xx does not abort the reservation; the item is marked `provider_failed` and the checkout continues in degraded mode.
- **Fail-closed on provider stock rejection** — if the external warehouse returns 409 Insufficient Stock, the entire reservation is rolled back.
- **Background sweep** — an `APScheduler` job runs every 60 seconds (configurable), finds expired pending reservations, releases their inventory and marks them `expired`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | python-jose (JWT) + bcrypt |
| HTTP client | httpx (async) |
| Scheduling | APScheduler 3.x (`AsyncIOScheduler`) |
| DB — production | MySQL 8 via `aiomysql` |
| DB — tests | SQLite in-memory via `aiosqlite` |
| Testing | pytest + pytest-asyncio + httpx + respx |
| Linting/formatting | ruff |
| Type checking | mypy |

---

## System Architecture

```
HTTP Client
    │
    ▼
FastAPI app (main.py)
    │
    ├── RequestLoggingMiddleware   — assigns request_id, logs request + duration
    ├── CORSMiddleware
    │
    ├── /api/v1/reservations       ── ReservationService
    ├── /api/v1/inventory          ── InventoryService
    ├── /api/v1/providers          ── InventoryService
    ├── /api/v1/orders             ── OrderService / ReservationService
    └── /api/v1/auth               ── UserService
                │
                ▼
        Service Layer
                │
          ┌─────┴──────┐
          ▼            ▼
    Repository     ProviderRegistry
    (SQLAlchemy)        │
          │        ┌────┴────────────┐
          ▼        ▼                 ▼
       MySQL   InternalProvider  ExternalHttpProvider
               (reads DB rows)   (httpx → warehouse API)

Background:
    AsyncIOScheduler ──every 60s──▶ _run_expiry_sweep
                                        │
                                        ▼
                                 ReservationService.expire_batch()
```

### Layer responsibilities

| Layer | Location | Responsibility |
|---|---|---|
| Routers | `app/api/v1/routers/` | HTTP ↔ schema translation, dependency injection |
| Services | `app/services/` | Business logic, orchestration, transaction boundary |
| Repositories | `app/repositories/` | SQL queries, locking primitives |
| Providers | `app/providers/` | External stock operations (hold, confirm, release, check) |
| Models | `app/models/` | SQLAlchemy ORM definitions |
| Schemas | `app/schemas/` | Pydantic request/response contracts |
| Workers | `app/workers/` | Background jobs (expiry sweep) |

---

## Data Model

```
products
  id, name, sku (unique), created_at, updated_at

inventory_providers
  id, name (unique), type (internal|external), capabilities (JSON),
  auth_config (JSON), base_url, timeout_seconds, is_active,
  created_at, updated_at

inventory
  id, product_id → products, provider_id → inventory_providers,
  qty_available, qty_reserved, last_synced_at, created_at, updated_at
  UNIQUE (product_id, provider_id)
  INDEX (product_id), INDEX (provider_id)

reservations
  id, user_id, status (pending|confirmed|cancelled|expired),
  expires_at, created_at, updated_at
  INDEX (status, expires_at)   ← expiry sweep uses this
  INDEX (user_id)

reservation_items
  id, reservation_id → reservations (CASCADE DELETE),
  product_id → products, inventory_id → inventory,
  provider_id → inventory_providers,
  qty_requested, provider_hold_ref, provider_status, provider_error_message,
  created_at, updated_at
  INDEX (reservation_id)

orders
  id, reservation_id → reservations (UNIQUE),
  user_id, status (created|fulfilled|failed), created_at, updated_at
  INDEX (user_id)

users
  id, email (unique), username (unique), full_name,
  hashed_password, is_active, created_at, updated_at
```

### Inventory counters

Every `inventory` row tracks two counters:

| Counter | Meaning |
|---|---|
| `qty_available` | Physical stock at the provider (updated by sync) |
| `qty_reserved` | Units locked by active `pending` reservations |
| `effective = qty_available - qty_reserved` | Units a new buyer can actually get |

When a reservation is created, `qty_reserved` increases. When confirmed, `qty_available` and `qty_reserved` both decrease. When cancelled or expired, `qty_reserved` decreases.

---

## API Reference

All endpoints are under `/api/v1`. Every response uses the same JSON envelope:

```json
// success
{ "success": true,  "code": 200, "message": "Ok", "data": { ... } }
{ "success": true,  "code": 201, "message": "Created", "data": { ... } }

// failure
{ "success": false, "code": 404, "message": "Not Found", "error": { "detail": "..." }, "request_id": "..." }
{ "success": false, "code": 422, "message": "Validation Exception", "error": { "field": ["msg"] } }
```

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/signup` | Public | Register a new user |
| POST | `/api/v1/auth/login` | Public | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Public | Rotate access token using refresh token |
| POST | `/api/v1/auth/logout` | Bearer | Client-side token discard |
| GET | `/api/v1/auth/profile` | Bearer | Get current user |
| PATCH | `/api/v1/auth/profile` | Bearer | Update profile |

### Reservations

| Method | Path | Status | Description |
|---|---|---|---|
| POST | `/api/v1/reservations` | 201 / 409 | Create a new reservation |
| GET | `/api/v1/reservations/{id}` | 200 / 404 | Get reservation with items |
| POST | `/api/v1/reservations/{id}/confirm` | 200 / 422 | Confirm (admin shortcut) |
| POST | `/api/v1/reservations/{id}/cancel` | 204 / 404 | Cancel and release inventory |

**Create reservation request:**
```json
{
  "user_id": "user_123",
  "items": [
    { "product_id": 1, "qty": 2 },
    { "product_id": 3, "qty": 1 }
  ]
}
```
Validation: duplicate `product_id` values in `items` are rejected with 422.

**Error codes:**
- `409` — insufficient stock (`InsufficientStockError`)
- `404` — reservation not found (`ReservationNotFound`)
- `422` — state machine violation e.g. confirming a cancelled reservation (`ReservationStateError`)

### Payment Outcome & Orders

| Method | Path | Status | Description |
|---|---|---|---|
| POST | `/api/v1/payment-outcome` | 200 / 422 | Notify payment result (success → confirm, failed → cancel) |
| GET | `/api/v1/orders/{id}` | 200 / 404 | Get order by ID |

**Payment outcome request:**
```json
{ "reservation_id": 42, "outcome": "success" }
{ "reservation_id": 42, "outcome": "failed" }
```
`outcome: "success"` → calls `ReservationService.confirm()` → returns `OrderResponse`.
`outcome: "failed"` → calls `ReservationService.cancel()` → returns `{ reservation_id, status: "cancelled" }`.

### Inventory

| Method | Path | Status | Description |
|---|---|---|---|
| GET | `/api/v1/inventory/{product_id}/availability` | 200 | Availability per provider for a product |

**Response example:**
```json
{
  "product_id": 1,
  "sources": [
    {
      "provider_id": 2,
      "provider_name": "WarehouseProvider",
      "qty_available": 12,
      "qty_reserved": 3,
      "effective_available": 9,
      "last_synced_at": "2026-06-22T10:00:00Z"
    }
  ]
}
```

### Providers

| Method | Path | Status | Description |
|---|---|---|---|
| POST | `/api/v1/providers/{provider_id}/sync` | 200 / 404 | Pull fresh stock counts from external provider |

**Response example:**
```json
{ "updated": 5, "errors": ["SKU-XYZ: connection timeout"], "message": "" }
```

---

## Reservation Lifecycle

```
           POST /reservations
                  │
          ┌───────▼────────┐
          │    pending      │ ← inventory locked (qty_reserved++)
          │  expires_at set │
          └────────┬────────┘
                   │
         ┌─────────┼──────────┐
         │         │          │
  payment/success  │   payment/failed   TTL expired
         │         │          │         (background sweep)
         ▼         │          ▼         │
   ┌──────────┐    │   ┌────────────┐   │
   │confirmed │    │   │ cancelled  │   │
   │ Order    │    │   │(inventory  │   │
   │ created  │    │   │ released)  │   │
   └──────────┘    │   └────────────┘   ▼
                   │             ┌──────────┐
                   │             │ expired  │
                   │             │(inventory│
                   └─────────────│ released)│
                                 └──────────┘
```

**State transition rules:**
- `pending` → `confirmed`: via `confirm()` — inventory permanently decremented
- `pending` → `cancelled`: via `cancel()` — `qty_reserved` released, provider `release_hold` called
- `pending` → `expired`: via `expire_batch()` — same release logic as cancel
- `confirmed` / `cancelled` / `expired` → any: blocked (raises `ReservationStateError`)
- `cancel()` on `cancelled` or `expired`: silently no-ops (idempotent)

---

## Provider System

All inventory providers implement `BaseProviderAdapter`:

```python
class BaseProviderAdapter(ABC):
    async def check_stock(self, sku: str) -> int: ...
    async def hold_stock(self, sku: str, qty: int, reservation_id: int) -> str | None: ...
    async def release_hold(self, hold_ref: str) -> bool: ...
    async def confirm_hold(self, hold_ref: str) -> None: ...
```

### InternalProviderAdapter

Reads and mutates `Inventory` model fields in-memory within the same DB transaction. No network call.

- `check_stock` → `qty_available - qty_reserved`
- `hold_stock` → verifies sufficient stock, returns `None` (no external hold ref)
- `release_hold` / `confirm_hold` → no-ops (managed by SQL)

### ExternalHttpProviderAdapter

Calls a remote warehouse API via `httpx.AsyncClient`. Reads `base_url`, `timeout_seconds`, and `auth_config` from the `InventoryProvider` row.

| HTTP call | Endpoint | Maps to |
|---|---|---|
| `check_stock` | `GET /stock/{sku}` | Returns `stock_level` |
| `hold_stock` | `POST /holds` | Returns `hold_id` as `hold_ref` |
| `release_hold` | `DELETE /holds/{ref}` | Returns `True`/`False` |
| `confirm_hold` | `POST /holds/{ref}/confirm` | — |

**Error mapping:**

| HTTP condition | Exception |
|---|---|
| `httpx.TimeoutException` | `ProviderTimeout` |
| 5xx response | `ProviderUnavailable` |
| 409 response | `InsufficientProviderStock` |

### Fail-open / Fail-closed behaviour

| Exception | Behaviour |
|---|---|
| `ProviderTimeout` / `ProviderUnavailable` | Item marked `provider_failed`, reservation continues |
| `InsufficientProviderStock` | Entire reservation rolled back with `409` |

### ProviderRegistry

```python
ProviderRegistry.resolve(provider, inventory_row=None) -> BaseProviderAdapter
```

Routes to `InternalProviderAdapter` or `ExternalHttpProviderAdapter` based on `provider.type`. Raises `ValueError` if `type=internal` is called without `inventory_row`.

---

## Concurrency Design

### Two-phase locking (oversell prevention)

```
Phase 1 — Pre-flight (no lock):
  get_best_available(product_id)   → ORDER BY (qty_available - qty_reserved) DESC LIMIT 1
  Check effective_available >= requested_qty
  Fast rejection — avoids acquiring DB locks unnecessarily

Phase 2 — Lock + re-check:
  get_by_id_for_update(inv_id)     → SELECT ... FOR UPDATE
  Re-check effective_available under lock
  Increment qty_reserved

Phase 3 — Provider hold:
  Call hold_stock() on the adapter
  If InsufficientProviderStock → raise (whole transaction rolls back)
  If ProviderTimeout/Unavailable → continue (fail-open, item marked degraded)
```

### Expiry sweep (`SKIP LOCKED`)

`get_expired_pending()` uses `SELECT ... FOR UPDATE SKIP LOCKED`:
- Multiple replicas can run the sweep simultaneously — each grabs its own non-overlapping batch
- No replica blocks waiting for rows another is processing
- `max_instances=1` and `coalesce=True` on the APScheduler job prevents a single replica from queuing up backlogged sweep runs

---

## Background Expiry Worker

The expiry worker runs inside the FastAPI lifespan (started on boot, stopped on shutdown):

```python
# main.py
start_expiry_scheduler(
    session_factory=AsyncSessionLocal,
    interval_seconds=settings.EXPIRY_SWEEP_INTERVAL_SECONDS,  # default: 60
)
```

Each run:
1. Opens a new database session
2. Calls `ReservationService.expire_batch(limit=100)` — finds up to 100 expired pending reservations
3. For each: releases `qty_reserved`, calls `release_hold()` on the provider (non-fatal), marks status `expired`
4. Commits the transaction
5. On any exception: rolls back and logs — never propagates to prevent crashing the scheduler

Control knobs (`config.py` / `.env`):

| Setting | Default | Effect |
|---|---|---|
| `RESERVATION_TTL_MINUTES` | `15` | How long a `pending` reservation lives |
| `EXPIRY_SWEEP_INTERVAL_SECONDS` | `60` | How often the sweep runs |

---

## Getting Started

### Prerequisites

- Python 3.12+
- MySQL 8.0 (or Docker)

### Local setup (without Docker)

```bash
# 1. Clone and enter directory
git clone <repo-url> && cd bimebazar-test

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY at minimum

# 5. Run migrations
alembic upgrade head

# 6. Seed initial data (providers + sample inventory)
python seed.py

# 7. Start the dev server
python run.py
# API at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

### Docker (recommended)

```bash
# 1. Configure
cp .env.example .env    # set SECRET_KEY; DATABASE_URL is auto-set by docker-compose

# 2. Build and start (app + MySQL)
docker compose up --build

# 3. App is at http://localhost:8000 — migrations + seed run automatically on startup
```

**Docker commands:**

```bash
docker compose up -d                             # run in background
docker compose logs -f app                       # follow app logs
docker compose down                              # stop, keep DB volume
docker compose down -v                           # stop, delete DB volume

docker compose exec app alembic upgrade head     # run migrations manually
docker compose exec app python seed.py           # re-run seed
docker compose exec app python manage.py seed:list
```

---

## Configuration

All settings are in `app/core/config.py` (Pydantic Settings) and loaded from `.env`:

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `MyApp` | Name shown in Swagger UI |
| `APP_VERSION` | `1.0.0` | Version string |
| `PRODUCTION` | `false` | Hides `/docs`, `/redoc`, `/openapi.json` when `true` |
| `DEBUG` | `false` | Extra debug output |
| `SERVER_LISTEN_IP` | `0.0.0.0` | Bind address |
| `SERVER_LISTEN_PORT` | `8000` | Port |
| `SERVER_WORKERS` | `1` | Uvicorn worker processes |
| `DATABASE_URL` | — | Async MySQL: `mysql+aiomysql://user:pass@host:port/db` |
| `SECRET_KEY` | — | JWT signing key — min 32 chars in production |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `RATE_LIMIT_ENABLED` | `true` | Toggle per-IP rate limiter (disable in tests) |
| `RESERVATION_TTL_MINUTES` | `15` | How long a pending reservation survives |
| `EXPIRY_SWEEP_INTERVAL_SECONDS` | `60` | Expiry sweep cadence |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SEED_ADMIN_EMAIL` | `admin@example.com` | First admin user email |
| `SEED_ADMIN_PASSWORD` | `Admin1234` | First admin user password |

### Generating a SECRET_KEY

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

The app refuses to start with `PRODUCTION=true` if `SECRET_KEY` is a known default or shorter than 32 characters.

---

## Database Migrations

Migrations are managed with Alembic. The migration history must never be deleted — always add forward migrations.

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration (after changing models)
alembic revision --autogenerate -m "describe_your_change"

# Rollback one step
alembic downgrade -1

# Check current revision
alembic current

# View migration history
alembic history
```

In development (non-production), `create_all` runs at startup as a fallback safety net. In production, only Alembic manages the schema.

### Schema summary

The `inventory-reservation-service` migration creates:

- `products` — product catalogue
- `inventory_providers` — internal and external stock sources
- `inventory` — stock levels per (product, provider) pair
- `reservations` — time-bounded checkout locks
- `reservation_items` — per-product line items within a reservation
- `orders` — confirmed purchase records

---

## Seed Data

`seed.py` runs all registered seeders in dependency order. Each seeder is idempotent.

```bash
python seed.py                                    # run all seeders
python manage.py seed:list                        # list available seeders
python manage.py seed:run inventory               # run one seeder by name
```

The `InventorySeeder` creates:

| Record | Type | Details |
|---|---|---|
| `InternalStock` provider | `internal` | Manages stock in-database |
| `WarehouseProvider` provider | `external` | `http://warehouse-api.example.com`, API key auth |
| Sony WH-1000XM5 (SKU: `SONY-WH1000XM5`) | Product | 12 units at WarehouseProvider |
| Anker USB-C Hub 7-in-1 (SKU: `ANKER-USBHUB-7IN1`) | Product | 340 units at InternalStock |

---

## Testing

The test suite uses SQLite in-memory — no MySQL, no Docker, no `.env` required.

```bash
# Run all tests
.venv/bin/pytest app/tests/ -q

# Verbose output
.venv/bin/pytest app/tests/ -v

# Single file
.venv/bin/pytest app/tests/test_services/test_reservation_service.py -q

# Single test
.venv/bin/pytest app/tests/test_services/test_reservation_service.py::test_create_success -q

# With coverage
.venv/bin/pytest app/tests/ --cov=app --cov-report=term-missing

# Full CI check (lint + types + tests)
make check
```

### Test structure

```
app/tests/
├── conftest.py                          # SQLite engine, db_session fixture, client fixture,
│                                        # auth_headers, clean_db (autouse, per-test isolation)
├── factories/
│   └── user_factory.py                  # make_user(), user_payload()
│
├── test_core/
│   └── test_rate_limit.py               # RateLimiter unit tests
│
├── test_providers/                      # Provider adapter tests (unit, respx mocks)
│   ├── test_internal_provider.py        # check_stock, hold_stock, release_hold
│   ├── test_external_provider.py        # httpx mocking via respx
│   ├── test_registry.py                 # ProviderRegistry.resolve() routing
│   └── test_scenarios.py                # End-to-end adapter scenarios (hold→confirm, timeout)
│
├── test_repositories/                   # Integration tests — real SQLite, no mocks
│   ├── test_inventory_repository.py     # get_best_available, get_by_id_for_update, etc.
│   ├── test_reservation_repository.py   # get_with_items, get_expired_pending
│   └── test_order_repository.py         # get_by_reservation_id
│
├── test_services/                       # Unit tests — AsyncMock repos
│   ├── test_reservation_service.py      # create, confirm, cancel, expire_batch (16 tests)
│   ├── test_inventory_service.py        # get_availability, sync_from_provider (10 tests)
│   └── test_order_service.py            # get_by_id found/not-found
│
├── test_workers/
│   └── test_expiry_worker.py            # _run_expiry_sweep, start/stop lifecycle (7 tests)
│
└── test_routes/                         # HTTP layer tests — dependency_overrides
    ├── test_auth_routes.py              # signup, login, refresh, logout, profile
    ├── test_reservation_routes.py       # POST/GET reservations, payment-outcome (16 tests)
    ├── test_inventory_routes.py         # GET availability (4 tests)
    ├── test_provider_routes.py          # POST sync (4 tests)
    └── test_order_routes.py             # GET order (5 tests)
```

**115 tests, all passing.**

### Key testing patterns

**Unit tests (services):** `AsyncMock` for all repos and adapters; `SimpleNamespace` for model stubs instead of `Model.__new__()` (avoids SQLAlchemy mapper state errors).

```python
inv_repo = AsyncMock(spec=InventoryRepository)
inv_repo.get_best_available = AsyncMock(return_value=SimpleNamespace(
    id=1, product_id=1, qty_available=10, qty_reserved=2, ...
))
```

**Integration tests (repositories):** Use the real `db_session` fixture — seed rows with `db.add()` + `await db.flush()`, then call repository methods against actual SQL.

**Route tests:** Override FastAPI dependency at the test level:

```python
@pytest.fixture(autouse=True)
def override_svc():
    mock = MagicMock()
    app.dependency_overrides[get_reservation_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_reservation_service, None)
```

**Provider tests (external):** Mock HTTP with `respx`:

```python
with respx.mock(base_url="http://wh.example.com") as mock:
    mock.post("/holds").mock(return_value=httpx.Response(200, json={"hold_id": "WH-abc"}))
    hold_ref = await adapter.hold_stock("SKU-001", 2, 42)
    assert hold_ref == "WH-abc"
```

---

## Project Structure

```
bimebazar-test/
│
├── main.py                          # App factory, lifespan, middleware, /health
├── run.py                           # Uvicorn entry point
├── manage.py                        # CLI: seeders + commands
├── seed.py                          # Seeder runner (used by entrypoint.sh)
├── alembic.ini                      # Alembic config
├── pyproject.toml                   # ruff + mypy + pytest config
├── pytest.ini                       # asyncio_mode=auto
├── Makefile                         # install / dev / test / lint / format / check / run
├── requirements.txt                 # Production deps
├── requirements-dev.txt             # Dev + test deps
├── .env.example                     # Environment template
├── docker-compose.yml               # App + MySQL
├── docker/
│   ├── Dockerfile                   # Multi-stage, non-root user
│   └── entrypoint.sh                # migrate → seed → start
│
├── ARCHITECTURE.md                  # System design document
├── SCALABILITY.md                   # Scaling analysis and strategies
│
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── router/__init__.py       # api_router (prefix /api/v1)
│   │       └── routers/
│   │           ├── auth_router.py       # /auth/*
│   │           ├── reservation_router.py # /reservations/*
│   │           ├── order_router.py       # /payment-outcome, /orders/*
│   │           ├── inventory_router.py   # /inventory/*
│   │           └── provider_router.py    # /providers/*
│   │
│   ├── core/
│   │   ├── config.py                # Pydantic settings (reads .env)
│   │   ├── dependencies.py          # FastAPI dependency factories
│   │   ├── exception_handler.py     # Domain exception → HTTP status mapping
│   │   ├── exceptions.py            # Exception hierarchy
│   │   ├── logging.py               # Structured logging setup
│   │   ├── middleware.py            # Request logging + request_id
│   │   ├── rate_limit.py            # In-memory fixed-window rate limiter
│   │   ├── response.py              # ok(), created(), no_content()
│   │   └── security.py              # JWT encode/decode, bcrypt
│   │
│   ├── db/
│   │   ├── session.py               # Async engine, session factory, get_db, check_db
│   │   └── pagination.py            # PaginationParams, Page[T], paginate()
│   │
│   ├── models/
│   │   ├── user.py                  # User model
│   │   ├── product.py               # Product model
│   │   ├── inventory_provider.py    # InventoryProvider + ProviderType enum
│   │   ├── inventory.py             # Inventory model (stock counters)
│   │   ├── reservation.py           # Reservation + ReservationStatus enum
│   │   ├── reservation_item.py      # ReservationItem + ProviderItemStatus enum
│   │   └── order.py                 # Order + OrderStatus enum
│   │
│   ├── repositories/
│   │   ├── base.py                  # BaseRepository[T]: get_by_id, get_all, create, delete
│   │   ├── user_repository.py       # get_by_email, get_by_username
│   │   ├── inventory_repository.py  # get_best_available, get_by_id_for_update, get_all_by_*
│   │   ├── reservation_repository.py # get_with_items, get_expired_pending (SKIP LOCKED)
│   │   └── order_repository.py      # get_by_reservation_id
│   │
│   ├── services/
│   │   ├── base.py                  # BaseService[T]
│   │   ├── user_service.py          # Registration, login, profile update
│   │   ├── reservation_service.py   # create, confirm, cancel, expire_batch, get_with_items
│   │   ├── inventory_service.py     # get_availability, sync_from_provider
│   │   └── order_service.py         # get_by_id
│   │
│   ├── schemas/
│   │   ├── user.py                  # UserSignupRequest, UserLoginRequest, UserResponse, ...
│   │   ├── reservation.py           # ReservationCreateRequest, ReservationResponse, ...
│   │   ├── order.py                 # PaymentOutcomeRequest, OrderResponse
│   │   ├── inventory.py             # ProductAvailabilityResponse, InventoryAvailabilityItem
│   │   └── provider.py              # ProviderSyncResponse
│   │
│   ├── providers/
│   │   ├── base.py                  # BaseProviderAdapter ABC + exceptions
│   │   ├── internal.py              # InternalProviderAdapter (DB-backed)
│   │   ├── external_http.py         # ExternalHttpProviderAdapter (httpx)
│   │   └── registry.py              # ProviderRegistry.resolve()
│   │
│   ├── workers/
│   │   └── expiry_worker.py         # _run_expiry_sweep, start/stop_expiry_scheduler
│   │
│   ├── seeders/
│   │   ├── base.py                  # BaseSeeder
│   │   ├── kernel.py                # SEEDERS list (run order)
│   │   └── inventory_seeder.py      # Seeds providers + products + inventory
│   │
│   ├── commands/
│   │   ├── base.py                  # BaseCommand
│   │   └── kernel.py                # COMMANDS + SCHEDULE lists
│   │
│   ├── migrations/
│   │   ├── env.py                   # Alembic async env
│   │   └── versions/
│   │       └── *_inventory_reservation_schema.py
│   │
│   └── tests/
│       └── (see Testing section above)
│
└── openspec/
    └── changes/
        └── inventory-reservation-service/
            ├── proposal.md          # Original design proposal
            ├── tasks.md             # 70 implementation tasks (all done)
            ├── design.md            # Detailed design decisions
            └── specs/               # Per-feature spec files
```

---

## Scalability Notes

See [`SCALABILITY.md`](SCALABILITY.md) for the full analysis. Key points:

- **Stateless app tier** — no in-process state; scale horizontally behind any load balancer
- **Row-level locking** — `SELECT FOR UPDATE` contention is per-inventory-row, not table-wide
- **Async I/O** — single worker handles hundreds of concurrent requests without blocking threads
- **SKIP LOCKED sweep** — multiple replicas can run expiry sweeps simultaneously without coordination
- **Flash sale mitigation** — for extremely hot SKUs, a Redis atomic counter fronts the DB lock to shed load early
- **Read replicas** — availability queries (`GET /inventory`) can route to replicas; write path stays on primary
- **Circuit breakers** — external provider calls should wrap in a circuit breaker (e.g. `pybreaker`) to prevent cascade failures

See also [`ARCHITECTURE.md`](ARCHITECTURE.md) for the system design document.
