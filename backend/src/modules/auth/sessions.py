import secrets

from fastapi import Request
from redis import Redis

from common.config import settings
from modules.auth.exceptions import SessionRequiredError
from modules.auth.schemas import UserResponse

# Keep replacement and expiry refresh atomic so an old device cannot revive its session.
REPLACE_SESSION = """
local previous = redis.call('GET', KEYS[1])
if previous then redis.call('DEL', ARGV[1] .. previous) end
redis.call('HSET', KEYS[2], 'user_id', ARGV[3], 'username', ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[5])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[5])
return 1
"""

REFRESH_SESSION = """
local uid = redis.call('HGET', KEYS[1], 'user_id')
if not uid then return {} end
local pointer = ARGV[1] .. uid
if redis.call('GET', pointer) ~= ARGV[2] then return {} end
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('EXPIRE', pointer, ARGV[3])
return {uid, redis.call('HGET', KEYS[1], 'username')}
"""

DELETE_SESSION = """
local uid = redis.call('HGET', KEYS[1], 'user_id')
if uid then
    local pointer = ARGV[1] .. uid
    if redis.call('GET', pointer) == ARGV[2] then redis.call('DEL', pointer) end
end
redis.call('DEL', KEYS[1])
return 1
"""


class SessionStore:
    session_prefix = "apply_pilot:session:"
    user_prefix = "apply_pilot:user_session:"

    def __init__(self, redis: Redis):
        self.redis = redis

    def create(self, user: UserResponse) -> str:
        # Session credentials are random and independent of public account UUIDs.
        token = secrets.token_urlsafe(32)
        self.redis.eval(
            REPLACE_SESSION, 2, self.user_prefix + str(user.id), self.session_prefix + token,
            self.session_prefix, token, str(user.id), user.username, settings.session_ttl_seconds,
        )
        return token

    def get(self, token: str | None) -> UserResponse:
        if not token:
            raise SessionRequiredError("Please log in again")
        values = self.redis.eval(
            REFRESH_SESSION, 1, self.session_prefix + token,
            self.user_prefix, token, settings.session_ttl_seconds,
        )
        if not values:
            raise SessionRequiredError("Please log in again")
        return UserResponse(id=values[0], username=values[1])

    def delete(self, token: str | None) -> None:
        if token:
            # A stale device must never invalidate a newer device's login.
            self.redis.eval(DELETE_SESSION, 1, self.session_prefix + token, self.user_prefix, token)


def get_session_store(request: Request):
    return SessionStore(request.app.state.redis)
