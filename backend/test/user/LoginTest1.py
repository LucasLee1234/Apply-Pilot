import uuid

from redis import Redis

from common.config import Settings, settings
from modules.auth.schemas import UserResponse
from modules.auth.sessions import SessionStore

redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)

store = SessionStore(redis)

token = store.create(UserResponse(id=uuid.UUID("eda60678-cf24-45bf-8e43-c70701464b23"), username="test2"))

print(token)

redis.close()