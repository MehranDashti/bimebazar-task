import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVER_LISTEN_IP,
        port=settings.SERVER_LISTEN_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
        reload=not settings.PRODUCTION,
        loop="asyncio",
        workers=settings.SERVER_WORKERS,
    )
