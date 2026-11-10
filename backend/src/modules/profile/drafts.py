import uuid
from datetime import datetime, timezone

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError

from common.config import settings
from modules.profile.exceptions import DraftConflictError, DraftStorageError, DraftTooLargeError
from modules.profile.schemas import ProfileDraftData, ProfileDraftResponse, SaveProfileDraftRequest


SAVE_DRAFT = """
local current = redis.call('HGET', KEYS[1], 'version')
if current then
    if current ~= ARGV[1] then return {0} end
    if redis.call('PTTL', KEYS[1]) <= 0 then return {-1} end
elseif ARGV[1] ~= '' then
    return {0}
end
local now = redis.call('TIME')[1]
if not current then
    redis.call('HSET', KEYS[1], 'created_at', now,
        'expires_at', tonumber(now) + tonumber(ARGV[5]), 'user_id', ARGV[3])
end
redis.call('HSET', KEYS[1], 'version', ARGV[2], 'data', ARGV[4], 'updated_at', now)
if not current then redis.call('EXPIRE', KEYS[1], ARGV[5]) end
return {1, redis.call('HGETALL', KEYS[1])}
"""

DELETE_DRAFT ="""
local current = redis.call('HGET', KEYS[1], 'version')

if not current then
    return {2}
end

if current ~= ARGV[1] then
    return {0}
end

return {redis.call('DEL', KEYS[1])}
"""


class ProfileDraftStore:
    prefix = "apply_pilot:profile_draft:"

    def __init__(self, redis: Redis, ttl_seconds: int | None = None):
        self.redis = redis
        self.ttl_seconds = settings.profile_draft_ttl_seconds if ttl_seconds is None else ttl_seconds
        if self.ttl_seconds <= 0:
            raise ValueError("Draft retention must be positive")

    def get(self, user_id: uuid.UUID) -> dict[str, str] | None:
        try:
            return self.redis.hgetall(self.prefix + str(user_id)) or None
        except RedisError as exc:
            raise DraftStorageError("Draft storage is unavailable. Please try again later.") from exc

    def save(self, user_id: uuid.UUID, expected_version: uuid.UUID | None, data: str) -> dict[str, str]:
        try:
            # Keep data as an opaque JSON string: Lua must not alter empty arrays or numbers.
            result = self.redis.eval(
                SAVE_DRAFT, 1, self.prefix + str(user_id),
                str(expected_version) if expected_version else "", str(uuid.uuid4()),
                str(user_id), data, self.ttl_seconds,
            )
        except RedisError as exc:
            raise DraftStorageError("Draft storage is unavailable. Please try again later.") from exc
        if result[0] == 0:
            raise DraftConflictError("Draft changed or expired. Reload it before saving again.")
        if result[0] != 1:
            raise DraftStorageError("Draft expiration is invalid. Please try again later.")
        fields = result[1]
        return dict(zip(fields[::2], fields[1::2]))

    def delete_old_draft(self, user_id: uuid.UUID, current_version: uuid.UUID) -> int:
        try:
            result = self.redis.eval(
                DELETE_DRAFT, 1, self.prefix + str(user_id),
                str(current_version) if current_version else ""
            )
        except RedisError as exc:
            raise DraftStorageError("Draft storage is unavailable. Please try again later.") from exc
        if result[0] not in (0, 1, 2):
            raise DraftStorageError("Unexpected draft cleanup result.")
        return result[0]


class ProfileDraftService:
    def __init__(self, store: ProfileDraftStore):
        self.store = store

    def get_draft(self, user_id: uuid.UUID) -> ProfileDraftResponse | None:
        stored = self.store.get(user_id)
        return self._response(user_id, stored) if stored else None

    def save_draft(self, user_id: uuid.UUID, request: SaveProfileDraftRequest) -> ProfileDraftResponse:
        # PUT replaces the snapshot; exclude unset fields so incomplete input stays incomplete.
        data = request.data.model_dump_json(exclude_unset=True)
        if len(data.encode("utf-8")) > settings.profile_draft_max_bytes:
            raise DraftTooLargeError("Draft exceeds the allowed size.")
        stored = self.store.save(user_id, request.expected_version, data)
        return self._response(user_id, stored)

    def remove_existing_draft(self, user_id: uuid.UUID, current_version: uuid.UUID) -> int:
        # 0 preserves newer edits; 1 deleted this version; 2 was already absent.
        return self.store.delete_old_draft(user_id, current_version)

    @staticmethod
    def _response(user_id: uuid.UUID, stored: dict[str, str]) -> ProfileDraftResponse:
        try:
            if uuid.UUID(stored["user_id"]) != user_id:
                raise ValueError("Draft ownership mismatch")
            return ProfileDraftResponse(
                user_id=user_id, version=uuid.UUID(stored["version"]),
                created_at=datetime.fromtimestamp(int(stored["created_at"]), timezone.utc),
                updated_at=datetime.fromtimestamp(int(stored["updated_at"]), timezone.utc),
                expires_at=datetime.fromtimestamp(int(stored["expires_at"]), timezone.utc),
                data=ProfileDraftData.model_validate_json(stored["data"]),
            )
        except (KeyError, ValueError, TypeError, OverflowError, OSError) as exc:
            raise DraftStorageError("Stored draft is invalid. Please try again later.") from exc


def get_profile_draft_store(request: Request) -> ProfileDraftStore:
    return ProfileDraftStore(request.app.state.redis)
