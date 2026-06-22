# FastAPI Blueprint

A production-ready FastAPI starter template with async SQLAlchemy, JWT auth, in-memory rate limiting, pagination, filtering, seeder system, command scheduler, and full test coverage.

Copy this repo to start a new project — everything is wired up. Add models, delete what you don't need.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12 |
| Framework | FastAPI |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | python-jose + bcrypt |
| DB (production) | MySQL via aiomysql |
| DB (tests) | SQLite via aiosqlite |
| Testing | pytest + pytest-asyncio + httpx + faker |
| Scheduling | croniter (cron expression matching) |

---

## What's Included

### Core infrastructure

| Package | What it does |
|---------|-------------|
| `app/core/config.py` | Pydantic-settings — reads `.env`, typed settings, `SECRET_KEY` guard in production |
| `app/core/exceptions.py` | Domain exception hierarchy (`NotFoundError`, `ConflictError`, `AuthenticationError`, `InactiveAccountError`) |
| `app/core/exception_handler.py` | Translates domain exceptions → consistent JSON envelope with `request_id` |
| `app/core/response.py` | `ok()`, `created()`, `no_content()` — uniform response helpers |
| `app/core/security.py` | JWT access + refresh tokens, bcrypt password hashing |
| `app/core/rate_limit.py` | Zero-dependency in-memory rate limiter (fixed window, per-IP + path) |
| `app/core/dependencies.py` | `get_current_user`, `get_current_user_optional`, service dependency factories |
| `app/core/logging.py` | Structured console + syslog logging |
| `app/core/middleware.py` | `RequestLoggingMiddleware` — logs every request with UUID and duration |
| `app/db/session.py` | Async engine, session factory, `get_db` dependency, `check_db()` |
| `app/db/pagination.py` | `PaginationParams`, `Page[T]`, `paginate()` |
| `app/filters/base.py` | `BaseFilter` — composable query-param filtering + sorting |

### Domain (example resource)

The blueprint ships one complete reference resource (`Example`) wired through every layer. Copy it when adding your own domain models, then delete it.

| Layer | Files |
|-------|-------|
| Models | `app/models/user.py`, `app/models/example.py` |
| Repositories | `app/repositories/user_repository.py`, `app/repositories/example_repository.py` |
| Services | `app/services/user_service.py`, `app/services/example_service.py` |
| Schemas | `app/schemas/user.py`, `app/schemas/example.py` |
| Filters | `app/filters/example_filter.py` |
| Routers | `app/api/v1/routers/auth_router.py`, `app/api/v1/routers/example_router.py` |

### Supporting systems

| System | Location | Docs |
|--------|----------|------|
| Seeder system | `app/seeders/` | See [Seeder System](#seeder-system) below |
| Command scheduler | `app/commands/` | See [Command Scheduler](#command-scheduler) below |
| Test infrastructure | `app/tests/` | See [Tests](#tests) below |
| Docker setup | `docker/`, `docker-compose.yml` | See [Docker](#docker) below |

---

## Starting a New Project from This Blueprint

```bash
# 1. Copy to your new project directory
cp -r /path/to/fastapi-blueprint /path/to/my-new-project
cd /path/to/my-new-project

# 2. Init a new git repo
git init && git add . && git commit -m "init: from fastapi-blueprint"

# 3. Create your .env
cp .env.example .env
# Set DATABASE_URL, SECRET_KEY (min 32 chars), APP_NAME

# 4. Install dependencies
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# 5. Run migrations and seed
alembic upgrade head
python seed.py

# 6. Start the server
python run.py
```

Or use Docker — see [Docker](#docker) below.

---

## Quick Start (Docker)

```bash
cp .env.example .env        # set SECRET_KEY
docker compose up --build   # app at http://localhost:8000
```

---

## Configuration

All settings live in `app/core/config.py` and are read from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `MyApp` | Application name shown in Swagger |
| `DATABASE_URL` | — | Async MySQL connection string |
| `SECRET_KEY` | — | JWT signing key — min 32 random characters |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `PRODUCTION` | `false` | Disables `/docs`, `/redoc`, `/health` when `true` |
| `RATE_LIMIT_ENABLED` | `true` | Toggle in-memory rate limiter (set `false` in tests/CI) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SEED_ADMIN_EMAIL` | `admin@example.com` | Override before first `seed.py` run |
| `SEED_ADMIN_PASSWORD` | `Admin1234` | Override before first `seed.py` run |

### SECRET_KEY guard

`Settings` raises at startup if `PRODUCTION=true` and `SECRET_KEY` is a known default or shorter than 32 chars. Generate one with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

---

## Authentication

The blueprint includes JWT-based auth (no RBAC). Every authenticated user has equal access to protected routes.

| Endpoint | Method | Auth | Notes |
|----------|--------|------|-------|
| `/api/v1/auth/signup` | POST | Public | rate-limited 5 req/60 s |
| `/api/v1/auth/login` | POST | Public | rate-limited 10 req/60 s |
| `/api/v1/auth/refresh` | POST | Public | |
| `/api/v1/auth/logout` | POST | Authenticated | client-side token discard |
| `/api/v1/auth/profile` | GET | Authenticated | |
| `/api/v1/auth/profile` | PATCH | Authenticated | |

Logout is client-side only (token discard) — there is no server-side blacklist. Use Redis for true server-side revocation.

**To add RBAC:** add a `Role`/`Permission` model, a `require_permission(...)` dependency, and register permission names in a seeder.

---

## Rate Limiting

A zero-dependency, in-memory `RateLimiter` (fixed window keyed by client IP + path). No Redis or `slowapi` required.

```python
from fastapi import Depends
from app.core.rate_limit import RateLimiter

login_limiter = RateLimiter(times=10, seconds=60)

@router.post("/login", dependencies=[Depends(login_limiter)])
async def login(...): ...
```

Exceeding the limit raises `429` with a `Retry-After` header. Toggle with `RATE_LIMIT_ENABLED=false` in tests/CI. For multi-worker deployments, back the store with Redis.

---

## Response Envelope

Every response uses the same JSON envelope:

```json
{ "success": true,  "code": 200, "message": "Ok",      "data":  { ... } }
{ "success": true,  "code": 201, "message": "Created",  "data":  { ... } }
{ "success": false, "code": 404, "message": "Not Found","error": { "detail": "..." }, "request_id": "..." }
{ "success": false, "code": 422, "message": "Validation Exception", "error": { "field": ["msg"] } }
{ "success": false, "code": 429, "message": "Too Many Requests", "error": { "detail": "..." } }
```

Use the helpers in every route — never return raw dicts or Pydantic models:

```python
from app.core.response import ok, created, no_content

return ok(MySchema.model_validate(obj))
return created(MySchema.model_validate(obj))
return no_content()
```

---

## Adding a New Domain Resource

Mirror the `Example` resource end-to-end:

1. **Model** — `app/models/your_model.py`, register in `app/models/__init__.py`
2. **Migration** — `alembic revision --autogenerate -m "add your_model"`, then `alembic upgrade head`
3. **Repository** — `app/repositories/your_repository.py` extending `BaseRepository[YourModel]`
4. **Service** — `app/services/your_service.py` extending `BaseService[YourModel]`
5. **Schemas** — `app/schemas/your_model.py`
6. **Filter** — `app/filters/your_filter.py` extending `BaseFilter` + `YourFilterParams`
7. **Router** — `app/api/v1/routers/your_router.py`, include in `app/api/v1/router/__init__.py`
8. **Dependency** — add `get_your_service()` to `app/core/dependencies.py`
9. **Tests** — factories + test files under `app/tests/`

Run `make check` (ruff + mypy + pytest) before committing.

---

## Seeder System

Seeders live in `app/seeders/`. Each is a class; run all at once or one at a time.

```bash
python manage.py seed:list         # list registered seeders
python manage.py seed:run          # run all seeders (atomic transaction)
python manage.py seed:run examples # run a single seeder by name
```

### Creating a seeder

```python
# app/seeders/your_seeder.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.seeders.base import BaseSeeder

class YourSeeder(BaseSeeder):
    name = "your-seeder"
    description = "What this seeder creates"

    async def run(self, db: AsyncSession) -> None:
        pass  # idempotent DB logic
```

Register in `app/seeders/kernel.py` — append to `SEEDERS` in dependency order.

---

## Command Scheduler

Commands live in `app/commands/`. Copy `example_command.py` as a starting point.

```bash
python manage.py list                    # list all commands
python manage.py run example:run         # run a command manually
python manage.py schedule:run            # run commands due right now (cron)
```

Register in `app/commands/kernel.py`. Add a cron expression to `SCHEDULE` for automatic scheduling.

OS cron entry (runs every minute, Laravel-style):
```
* * * * * cd /path/to/project && venv/bin/python manage.py schedule:run >> /var/log/scheduler.log 2>&1
```

---

## Tests

38 tests, all passing. Tests use in-memory SQLite — no MySQL, no `.env`, no Docker required.

```bash
make test                # all tests
pytest -v                # verbose
pytest --tb=short        # short tracebacks
make check               # ruff + mypy + pytest (CI parity)
```

### Test structure

```
app/tests/
├── conftest.py                    # DB engine, fixtures, auth_headers, user_headers
├── factories/                     # Faker + uuid4 data factories (make_*, *_payload)
│   ├── user_factory.py
│   └── example_factory.py
├── test_core/
│   └── test_rate_limit.py         # RateLimiter unit tests (3)
├── test_repositories/
│   └── test_example_repository.py # Repository layer tests (6)
├── test_services/
│   └── test_example_service.py    # Service layer tests (7)
└── test_routes/
    ├── test_auth_routes.py        # Auth endpoint tests (13)
    └── test_example_routes.py     # Example endpoint tests (9)
```

### Factory pattern

```python
# DB fixture — persists to in-memory SQLite
example = await make_example(db_session)
example = await make_example(db_session, name="pinned")

# HTTP payload dict — for route tests
resp = await client.post("/api/v1/examples", headers=auth_headers, json=example_payload())
```

---

## Docker

```bash
cp .env.example .env            # set SECRET_KEY
docker compose up --build       # app + MySQL, auto-migrated and seeded
docker compose up -d            # background
docker compose logs -f app      # follow logs
docker compose down             # stop, preserve data
docker compose down -v          # stop, wipe data
docker compose exec app python manage.py seed:list
```

---

## Project Structure

```
fastapi-blueprint/
├── app/
│   ├── api/v1/
│   │   ├── router/          # Aggregated api_router (prefix /api/v1)
│   │   └── routers/
│   │       ├── auth_router.py
│   │       └── example_router.py
│   ├── commands/            # Scheduler commands (BaseCommand)
│   ├── seeders/             # DB seeders (BaseSeeder)
│   ├── core/                # Config, exceptions, auth, rate limiting, logging, response helpers
│   ├── db/                  # Session, Base, pagination
│   ├── filters/             # BaseFilter + per-resource FilterParams
│   ├── models/              # SQLAlchemy ORM models
│   ├── repositories/        # Data access (BaseRepository)
│   ├── services/            # Business logic (BaseService)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── migrations/          # Alembic env + versions/
│   └── tests/               # Full test suite
├── docker/
│   ├── Dockerfile           # Production image (cache-optimised, non-root)
│   └── entrypoint.sh        # migrate → seed → start
├── main.py                  # App factory, lifespan, middleware, /health
├── run.py                   # Uvicorn entry point
├── manage.py                # Commands + seeders CLI
├── seed.py                  # Thin seeder runner
├── docker-compose.yml
├── Makefile                 # install / dev / test / lint / format / typecheck / check / run
├── alembic.ini
├── pyproject.toml           # ruff, mypy, pytest config
├── pytest.ini
├── requirements.txt         # Production deps
├── requirements-dev.txt     # Dev/test deps
└── .env.example
```
