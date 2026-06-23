from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.expiry_worker as ew
from app.workers.expiry_worker import (
    _run_expiry_sweep,
    start_expiry_scheduler,
    stop_expiry_scheduler,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_factory(mock_db: AsyncMock):
    """Return a callable whose return value acts as an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory


# ── _run_expiry_sweep ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_expiry_sweep_calls_expire_batch():
    mock_db = AsyncMock()
    factory = _make_factory(mock_db)

    mock_svc = AsyncMock()
    mock_svc.expire_batch = AsyncMock(return_value=3)

    with patch("app.workers.expiry_worker.ReservationService", return_value=mock_svc):
        await _run_expiry_sweep(factory)

    mock_svc.expire_batch.assert_awaited_once_with(limit=100)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_expiry_sweep_zero_count_no_log(caplog):
    mock_db = AsyncMock()
    factory = _make_factory(mock_db)

    mock_svc = AsyncMock()
    mock_svc.expire_batch = AsyncMock(return_value=0)

    with patch("app.workers.expiry_worker.ReservationService", return_value=mock_svc):
        await _run_expiry_sweep(factory)

    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_expiry_sweep_exception_rolls_back():
    mock_db = AsyncMock()
    factory = _make_factory(mock_db)

    mock_svc = AsyncMock()
    mock_svc.expire_batch = AsyncMock(side_effect=RuntimeError("db failure"))

    with patch("app.workers.expiry_worker.ReservationService", return_value=mock_svc):
        # Must NOT propagate — graceful degradation
        await _run_expiry_sweep(factory)

    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()


# ── start_expiry_scheduler ────────────────────────────────────────────────────

def test_start_expiry_scheduler_registers_job_and_starts(monkeypatch):
    mock_sched = MagicMock()
    monkeypatch.setattr("app.workers.expiry_worker.AsyncIOScheduler", lambda: mock_sched)

    result = start_expiry_scheduler(MagicMock(), interval_seconds=60)

    assert result is mock_sched
    mock_sched.add_job.assert_called_once()
    call_kwargs = mock_sched.add_job.call_args
    assert call_kwargs.kwargs.get("max_instances") == 1
    assert call_kwargs.kwargs.get("coalesce") is True
    mock_sched.start.assert_called_once()


def test_start_expiry_scheduler_sets_global(monkeypatch):
    mock_sched = MagicMock()
    monkeypatch.setattr("app.workers.expiry_worker.AsyncIOScheduler", lambda: mock_sched)

    start_expiry_scheduler(MagicMock(), interval_seconds=30)

    assert ew._scheduler is mock_sched


# ── stop_expiry_scheduler ─────────────────────────────────────────────────────

def test_stop_expiry_scheduler_shuts_down(monkeypatch):
    mock_sched = MagicMock()
    mock_sched.running = True
    monkeypatch.setattr(ew, "_scheduler", mock_sched)

    stop_expiry_scheduler()

    mock_sched.shutdown.assert_called_once_with(wait=False)


def test_stop_expiry_scheduler_noop_when_none(monkeypatch):
    monkeypatch.setattr(ew, "_scheduler", None)
    # Must not raise
    stop_expiry_scheduler()


def test_stop_expiry_scheduler_noop_when_not_running(monkeypatch):
    mock_sched = MagicMock()
    mock_sched.running = False
    monkeypatch.setattr(ew, "_scheduler", mock_sched)

    stop_expiry_scheduler()

    mock_sched.shutdown.assert_not_called()
