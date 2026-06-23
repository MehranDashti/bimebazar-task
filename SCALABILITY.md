# Scalability — Inventory Reservation Service

## Current Design Choices that Enable Scale

### 1. Stateless Application Layer

The FastAPI service holds no in-process state between requests. Every request fetches its own DB session and discards it. This means horizontal scaling is a simple matter of launching additional replicas behind a load balancer — no session affinity required.

### 2. Row-Level Locking (not table-level)

`SELECT FOR UPDATE` locks individual inventory rows, not the entire `inventory` table. Two concurrent reservations for different products never block each other. Lock contention is bounded by the number of concurrent requests for the _same_ SKU.

### 3. `SKIP LOCKED` for Background Workers

The expiry sweep uses `FOR UPDATE SKIP LOCKED`, which means multiple replicas can run the sweep simultaneously without coordination overhead. Each replica claims a different batch of expired rows. This is safe to scale out linearly.

### 4. Two-Phase Lock Pattern

The pre-flight check (no lock, fast rejection) filters out obviously-failing requests _before_ acquiring any locks. Under high read load (many users browsing the same limited-stock item), most requests fail fast at the pre-flight stage without touching any locks.

### 5. Async I/O Throughout

FastAPI and SQLAlchemy async are non-blocking. A replica handling a slow external provider call does not block the event loop for other requests — it suspends and yields the thread. Provider timeouts are bounded by `timeout_seconds` per provider.

---

## Scaling Dimensions and Strategies

### Traffic Spikes (Flash Sales)

**Problem**: Many users simultaneously attempting to reserve the same SKU.

**Current mitigations**:
- Pre-flight check rejects invalid requests without acquiring DB locks
- `SELECT FOR UPDATE` serialises writes at the row level, not the service level

**Further options**:
1. **Redis distributed lock / counter**: Maintain a `qty_available` counter in Redis, decremented atomically with `DECR`. Use this as a fast pre-flight gate before hitting the DB. On miss, reject immediately. On hit, proceed to DB confirmation. This moves the hot path from MySQL to Redis.
2. **Request queue per SKU**: Funnel requests for the same SKU through a per-key queue (e.g. Redis BLPOP or a FIFO SQS queue) to serialise at the application layer and reduce DB lock contention.

### Read Scalability

**Problem**: `GET /inventory/{product_id}/availability` and `GET /reservations/{id}` under high read load.

**Options**:
1. **Read replicas**: Route `SELECT` queries to MySQL read replicas. SQLAlchemy async supports multiple bind configurations.
2. **Short-lived cache**: Cache `qty_available - qty_reserved` in Redis with a 5–10 second TTL. Stale reads are acceptable for availability checks (users see "10 in stock" vs "9 in stock"). Cache is invalidated on `create()` / `confirm()` / `cancel()`.

### Database Scalability

**Problem**: Single MySQL instance becomes a bottleneck.

**Current**: All tables on one MySQL 8 instance.

**Options**:
1. **Vertical scaling**: Increase instance size, enable InnoDB buffer pool tuning, add `innodb_lock_wait_timeout` tuning.
2. **Sharding**: Shard by `product_id` (range or hash). Each shard holds all reservations for a subset of products. Cross-product reservations (multiple items per basket) require a two-phase commit or saga pattern.
3. **CQRS**: Separate the write model (MySQL with locks) from the read model (Elasticsearch or a denormalised read store updated via CDC / binlog streaming).

### External Provider Calls

**Problem**: High-latency or flaky external provider APIs slow down reservation creation.

**Current mitigations**:
- Per-provider `timeout_seconds` config
- Fail-open: timeouts produce `provider_failed` items, not errors

**Options**:
1. **Async dispatch**: Move external provider `hold_stock` calls out of the request path. Create the reservation immediately (status=`pending_provider`), then dispatch provider calls via a task queue (Celery / RQ / Kafka). Poll or webhook when complete.
2. **Circuit breaker**: Track recent failure rates per provider. If a provider fails >X% of requests in a window, open the circuit and skip it (fail-open immediately without a timeout).
3. **Bulkhead isolation**: Give each provider its own `httpx.AsyncClient` with a dedicated semaphore to limit concurrent calls. Prevents one slow provider from monopolising all connections.

### Multi-Region

**Problem**: Users in different regions need low-latency reservation.

**Options**:
1. **Regional write proxies**: Route reservation writes to the nearest regional cluster, with eventual replication to a global coordinator for cross-region stock. Accept slightly stale reads in remote regions.
2. **Global inventory pool + per-region soft allocation**: Allocate a quota of stock to each region. Each region manages its quota independently; re-balancing happens asynchronously via a background job.

---

## Bottleneck Analysis

| Bottleneck | Likely at | Mitigation |
|---|---|---|
| DB lock contention on hot SKU | ~500 concurrent reservations / SKU | Redis atomic counter as pre-gate |
| MySQL connection pool exhaustion | ~1k concurrent requests per replica | PgBouncer equivalent (ProxySQL), replica reads |
| External provider timeout throughput | ~100 slow provider calls in flight | Async dispatch, circuit breaker |
| Expiry sweep latency | Millions of expired rows | Partition `reservations` by `status` + `expires_at`; increase batch size |

---

## Current Configuration Knobs

| Setting | Default | Notes |
|---|---|---|
| `RESERVATION_TTL_MINUTES` | 15 | Lower TTL → less inventory tied up; higher → better user experience |
| `EXPIRY_SWEEP_INTERVAL_SECONDS` | 60 | Lower → stock freed faster; higher → fewer DB sweeps |
| `provider.timeout_seconds` | per-provider | Trade-off between responsiveness and provider reliability |

---

## Observability for Scale

To detect scalability issues early:

- **DB lock wait metrics**: Monitor `innodb_row_lock_waits` and `innodb_row_lock_time_avg` in MySQL.
- **Reservation success rate**: Track `InsufficientStockError` rate; a sudden spike indicates hot-SKU contention.
- **Provider call latency**: Histogram of `hold_stock` / `confirm_hold` latency per provider.
- **Expiry lag**: Track the gap between `expires_at` and the actual expiry sweep timestamp. Growing lag means the sweep can't keep up.
- **Queue depth**: If async dispatch is added, monitor the task queue depth per provider.
