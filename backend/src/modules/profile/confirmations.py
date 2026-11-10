"""Review proposals and commit approved changes with durable replay protection."""

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from common.config import settings
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore
from modules.profile.exceptions import (
    ConfirmationNotFoundError, ConfirmationOwnershipError, ConfirmationStorageError,
    ConfirmationValidationError, DraftConflictError, DraftNotFoundError, ProfileVersionConflictError,
    DraftStorageError,
)
from modules.profile.preview_schemas import ProfileConfirmationRecord, ProfileConfirmationPayload
from modules.profile.receipts import ConfirmationReceiptRepository
from modules.profile.service import ApplicantProfileService
from modules.profile.utils import get_fingerprint, read_baseline, SECTIONS

logger = logging.getLogger(__name__)

OPERATIONS = {
    "REMOVE": "remove",
    "ADD": "add",
    "UPDATE": "update"
}

CREATE_CONFIRMATION = """
if redis.call('HGET', KEYS[1], 'version') ~= ARGV[1] then return {0} end
local remaining = math.floor(redis.call('PTTL', KEYS[1]) / 1000)
local ttl = math.min(remaining, tonumber(ARGV[4]))
if ttl <= 0 then return {0} end
if redis.call('EXISTS', KEYS[2]) ~= 0 then return {-1} end
local now = tonumber(redis.call('TIME')[1])
redis.call('HSET', KEYS[2], 'user_id', ARGV[2], 'draft_version', ARGV[1],
    'status', 'awaiting_confirmation', 'payload', ARGV[3],
    'created_at', now, 'expires_at', now + ttl)
redis.call('EXPIRE', KEYS[2], ttl)
return {1, now + ttl}
"""

CHANGE_CONFIRMATION_STATUS_AS_COMPLETED = """
local current = redis.call('HGET', KEYS[1], 'draft_version')
if not current then return {2} end
if current ~= ARGV[1] then return {0} end
local status = redis.call('HGET', KEYS[1], 'status')
if status ~= 'awaiting_confirmation' and status ~= 'processing' and status ~= ARGV[2] then
    return {0}
end
redis.call('HSET', KEYS[1], 'status', ARGV[2])
return {1}
"""

CLAIM_CONFIRMATION = """
if redis.call('EXISTS', KEYS[1]) == 0 then return {2} end
if redis.call('HGET', KEYS[1], 'draft_version') ~= ARGV[1] then return {0} end
if redis.call('HGET', KEYS[2], 'version') ~= ARGV[1] then return {3} end
local status = redis.call('HGET', KEYS[1], 'status')
if status ~= 'awaiting_confirmation' and status ~= 'processing' then return {0} end
redis.call('HSET', KEYS[1], 'status', 'processing')
return {1}
"""


class ProfileConfirmationStore:
    prefix = "apply_pilot:profile_confirmation:"

    def __init__(self, redis: Redis):
        self.redis = redis

    def create(self, user_id: uuid.UUID, draft_version: uuid.UUID, payload: str) -> tuple[str, datetime]:
        confirmation_id = secrets.token_urlsafe(32)
        # Scope the lookup by both authenticated owner and an unpredictable proposal token.
        key = self.prefix + str(user_id) + ":" + confirmation_id
        try:
            result = self.redis.eval(
                CREATE_CONFIRMATION, 2, ProfileDraftStore.prefix + str(user_id), key,
                str(draft_version), str(user_id), payload, settings.profile_confirmation_ttl_seconds,
            )
        except RedisError as exc:
            raise ConfirmationStorageError("Cannot prepare confirmation. Please try again later.") from exc
        if result[0] == 0:
            raise DraftConflictError("Draft changed or expired. Reload it before previewing again.")
        if result[0] != 1:
            raise ConfirmationStorageError("Cannot prepare confirmation. Please try again later.")
        return confirmation_id, datetime.fromtimestamp(int(result[1]), timezone.utc)

    def get(self, user_id: uuid.UUID, confirmation_id: str) -> dict[str, str] | None:
        key = self.prefix + str(user_id) + ":" + str(confirmation_id)
        try:
            return self.redis.hgetall(key) or None
        except RedisError as exc:
            raise ConfirmationStorageError("Confirmation storage is unavailable. Please try again later.") from exc

    def claim(self, user_id: uuid.UUID, confirmation_id: str, draft_version: uuid.UUID):
        """Must run while holding the per-user SQL transaction lock."""
        key = self.prefix + str(user_id) + ":" + confirmation_id
        try:
            result = self.redis.eval(
                CLAIM_CONFIRMATION, 2, key, ProfileDraftStore.prefix + str(user_id), str(draft_version),
            )
        except RedisError as exc:
            raise ConfirmationStorageError("Cannot claim confirmation. Please try again later.") from exc
        if result[0] == 2:
            raise ConfirmationNotFoundError("Confirmation expired. Preview again.")
        if result[0] == 3:
            raise DraftConflictError("Draft changed or expired. Preview again.")
        if result[0] != 1:
            raise ConfirmationValidationError("Confirmation is no longer available for approval.")

    def update_status(self, user_id: uuid.UUID, confirmation_id: str, draft_version: uuid.UUID,
                      *, status: str = "completed") -> int:
        if status not in ("completed", "cancelled"):
            raise ValueError("Unsupported final confirmation status")
        key = self.prefix + str(user_id) + ":" + str(confirmation_id)
        try:
            result = self.redis.eval(
                CHANGE_CONFIRMATION_STATUS_AS_COMPLETED, 1, key,
                str(draft_version), status,
            )
        except RedisError as exc:
            raise ConfirmationStorageError("Cannot set confirmation status. Please try again later.") from exc
        if result[0] == 0:
            raise ConfirmationValidationError("Confirmation changed before finalization.")
        if result[0] not in (1, 2):
            raise ConfirmationStorageError("Unexpected confirmation finalization result.")
        # Expired Redis state is harmless once a durable SQL outcome exists.
        return result[0]



class ConfirmationService:
    def __init__(self, store: ProfileConfirmationStore, draft_store: ProfileDraftStore, db: Session):
        self.store = store
        self.draft_store = draft_store
        self.draft_service = ProfileDraftService(draft_store)
        self.db = db
        self.profile_service = ApplicantProfileService(db)
        self.receipts = ConfirmationReceiptRepository(db)

    def get_confirmation(self, user_id: uuid.UUID, confirmation_id: str) -> ProfileConfirmationRecord | None:
        stored = self.store.get(user_id, confirmation_id)
        return self._response(user_id, stored) if stored else None

    def validate_confirmation(self, user_id: uuid.UUID, confirmation_id: str,
                              *, allow_processing: bool = False) -> ProfileConfirmationRecord:
        record = self.get_confirmation(user_id, confirmation_id)
        if record is None:
            raise ConfirmationNotFoundError("Confirmation not found or expired. Preview the changes again.")

        allowed = ("awaiting_confirmation", "processing") if allow_processing else ("awaiting_confirmation",)
        if record.status not in allowed:
            raise ConfirmationValidationError("Confirmation is no longer awaiting approval.")
        now = datetime.now(timezone.utc)
        if record.expires_at <= now:
            raise ConfirmationValidationError("Confirmation expired.")
        if record.user_id != user_id or record.payload.user_id != user_id:
            raise ConfirmationOwnershipError("Confirmation does not belong to the current user.")
        draft = self.draft_service.get_draft(user_id)
        if draft is None:
            raise DraftNotFoundError("Draft not found or expired. Save a draft and preview again.")
        if draft.expires_at <= now:
            raise DraftNotFoundError("Draft expired. Save a draft and preview again.")
        if record.draft_version != record.payload.draft_version or record.draft_version != draft.version:
            raise DraftConflictError("Draft version changed. Preview the latest draft again.")
        self.validate_formal_profile(user_id, record)
        # The record is already parsed; converting it as a Redis dictionary would fail.
        return record

    def validate_formal_profile(self, user_id: uuid.UUID,
                                record: ProfileConfirmationRecord) -> ProfileConfirmationRecord:
        """Read-only preflight; confirm also executes it while holding SQL locks."""
        if record.user_id != user_id or record.payload.user_id != user_id:
            raise ConfirmationOwnershipError("Confirmation does not belong to the current user.")
        current, baseline = read_baseline(self.db, user_id)
        current_version = current.version if current else None
        # None/None is valid for creation; every other unequal combination is stale.
        if current_version != record.payload.base_profile_version:
            raise ProfileVersionConflictError("Formal profile changed. Preview the latest profile again.")
        fingerprint = get_fingerprint(
            current_id=str(current.id) if current else None,
            base_version=current_version, baseline=baseline,
        )
        if fingerprint != record.payload.base_snapshot_hash:
            raise ProfileVersionConflictError("Formal profile contents changed. Preview the latest profile again.")
        return record


    def confirm(self, confirmation_id: str, user_id: uuid.UUID):
        try:
            self.receipts.lock(user_id)
            result = self.receipts.get(user_id, confirmation_id)
            if result is not None:
                if result["status"] != "completed":
                    raise ConfirmationValidationError("Confirmation was cancelled.")
                self.db.commit()
            else:
                # A processing proposal with no receipt can safely resume after a
                # rollback or crashed worker: the previous SQL lock is now released.
                record = self.validate_confirmation(
                    user_id=user_id, confirmation_id=confirmation_id, allow_processing=True,
                )
                self.store.claim(user_id, confirmation_id, record.draft_version)
                changes = self._change(record.payload.changes, user_id, record.payload.base_profile_version)
                self.profile_service.confirm_draft_save_applicant_information(changes, user_id, commit=False)
                if "profile" not in changes:
                    self.profile_service.applicant_profile_repository.bump_version(
                        user_id, record.payload.base_profile_version,
                    )
                saved = self.profile_service.obtain_complete_profile_by_user_id(user_id)
                result = {
                    "status": "completed", "draft_version": str(record.draft_version),
                    "profile_version": saved.profile.version, "saved": saved.model_dump(mode="json"),
                }
                self.receipts.add(user_id, confirmation_id, result)
                # Receipt and all profile writes succeed or roll back together.
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {**result, "cleanup": self._cleanup(user_id, confirmation_id, result)}

    def _cleanup(self, user_id: uuid.UUID, confirmation_id: str, result: dict) -> dict:
        version = uuid.UUID(result["draft_version"])
        cleanup = {}
        # Independent attempts: a Redis failure must not turn a committed save into
        # a failure. Repeating confirm reads the receipt and retries only cleanup.
        try:
            self.store.update_status(user_id, confirmation_id, version)
            cleanup["confirmation"] = "finalized_or_expired"
        except (ConfirmationStorageError, ConfirmationValidationError):
            cleanup["confirmation"] = "pending"
            logger.warning("Confirmation status cleanup pending")
        try:
            deleted = self.draft_service.remove_existing_draft(user_id, version)
            cleanup["draft"] = {0: "newer_draft_preserved", 1: "deleted", 2: "already_absent"}[deleted]
        except DraftStorageError:
            cleanup["draft"] = "pending"
            logger.warning("Profile draft cleanup pending")
        return cleanup

    def cancel(self, confirmation_id: str, user_id: uuid.UUID) -> dict:
        try:
            self.receipts.lock(user_id)
            result = self.receipts.get(user_id, confirmation_id)
            if result is None:
                record = self.get_confirmation(user_id, confirmation_id)
                if record is None:
                    raise ConfirmationNotFoundError("Confirmation not found or expired.")
                if record.status not in ("awaiting_confirmation", "processing", "cancelled"):
                    raise ConfirmationValidationError("Confirmation cannot be cancelled.")
                if record.expires_at <= datetime.now(timezone.utc):
                    raise ConfirmationValidationError("Confirmation expired.")
                result = {"status": "cancelled", "draft_version": str(record.draft_version)}
                self.receipts.add(user_id, confirmation_id, result)
            elif result["status"] != "cancelled":
                raise ConfirmationValidationError("Completed changes cannot be cancelled.")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        try:
            self.store.update_status(user_id, confirmation_id, uuid.UUID(result["draft_version"]), status="cancelled")
        except (ConfirmationStorageError, ConfirmationValidationError):
            # The durable cancelled receipt already prevents any subsequent write.
            logger.warning("Confirmation cancellation cache update pending")
        return result

    def _change(self, changes, user_id: uuid.UUID, base_profile_version: int | None) -> dict:
        format_changes = {}
        num = 0
        for change in changes:
            field = change.field
            if field.startswith("profile"):
                if format_changes.get("profile") is None:
                    format_changes["profile"] = {"data": {}}
                if format_changes["profile"].get("id") is None:
                    if base_profile_version is None:
                        format_changes["profile"]["id"] = ""
                    else:
                        current = self.profile_service.obtain_profile_by_user_id(user_id=user_id)
                        format_changes["profile"]["id"] = current.id
                name = change.field.split(".")[1].strip()
                format_changes["profile"]["data"][name] = change.after
                continue
            for section in SECTIONS:
                schema, _, _ = SECTIONS[section]
                if field.startswith(section):
                    if format_changes.get(section) is None:
                        format_changes[section] = {}
                    if change.operation == OPERATIONS["REMOVE"]:
                        format_changes[section]["remove:" + str(num)] = change.field.split("[")[1].split("]")[0]
                        num += 1
                    elif change.operation == OPERATIONS["ADD"]:
                        format_changes[section]["add:" + str(num)] = change.after
                        num += 1
                    elif change.operation == OPERATIONS["UPDATE"]:
                        id = field.split("[")[1].split("]")[0]
                        name = field.split(".")[1]
                        if format_changes[section].get(id) is None:
                            format_changes[section][id] = {}
                        format_changes[section][id][name] = change.after
                    else:
                        raise ConfirmationValidationError("Operation not supported.")
        return format_changes

    @staticmethod
    def _response(user_id: uuid.UUID, stored: dict[str, str]) -> ProfileConfirmationRecord:
        try:
            record = ProfileConfirmationRecord(
                user_id=stored["user_id"], draft_version=stored["draft_version"],
                created_at=datetime.fromtimestamp(int(stored["created_at"]), timezone.utc),
                expires_at=datetime.fromtimestamp(int(stored["expires_at"]), timezone.utc),
                status=stored["status"],
                payload=ProfileConfirmationPayload.model_validate_json(stored["payload"]),
            )
        except (KeyError, ValueError, TypeError, OverflowError, OSError) as exc:
            raise ConfirmationStorageError("Stored confirmation is invalid. Please try again later.") from exc
        if record.user_id != user_id or record.payload.user_id != user_id:
            raise ConfirmationOwnershipError("Confirmation does not belong to the current user.")
        return record


def get_profile_confirmation_store(request: Request) -> ProfileConfirmationStore:
    return ProfileConfirmationStore(request.app.state.redis)
