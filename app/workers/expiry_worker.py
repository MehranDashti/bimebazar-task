import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.providers.registry import ProviderRegistry
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.reservation_repository import ReservationRepository
from app.services.reservation_service import ReservationService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_expiry_sweep(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        try:
            svc = ReservationService(
                inv_repo=InventoryRepository(db),
                res_repo=ReservationRepository(db),
                order_repo=OrderRepository(db),
                registry=ProviderRegistry(),
            )
            count = await svc.expire_batch(limit=100)
            await db.commit()
            if count > 0:
                logger.info("expiry_sweep: expired %d reservations", count)
        except Exception:
            logger.exception("expiry_sweep: unhandled error — rolling back")
            await db.rollback()


def start_expiry_scheduler(
    session_factory: async_sessionmaker,
    interval_seconds: int,
) -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_expiry_sweep,
        trigger="interval",
        seconds=interval_seconds,
        kwargs={"session_factory": session_factory},
        id="expiry_sweep",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("expiry_scheduler: started (interval=%ds)", interval_seconds)
    return _scheduler


def stop_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("expiry_scheduler: stopped")
