import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from redis import Redis
from common.api_utils import create_app_api
from common.config import settings
from common.exception_handlers import register_exception_handlers
from modules.auth.route import router as auth_router
from modules.profile.route import router as profile_router

# Set up logging level and format
logging.basicConfig(
    level=settings.logging_level.upper(),
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s:%(lineno)d | %(message)s"
    ),
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,)

logger = logging.getLogger(__name__)

# Set up app lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Apply Pilot")
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
    try:
        yield
    finally:
        app.state.redis.close()
        logger.info("Finished Apply Pilot")

app = create_app_api(title="Apply Pilot", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(profile_router)

register_exception_handlers(app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
