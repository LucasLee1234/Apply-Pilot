import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from modules.profile.validation import FormalProfileSnapshot


class PreviewProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_version: uuid.UUID
    # Null means the caller expects that no formal profile exists yet.
    expected_profile_version: int | None = Field(ge=1, strict=True)


class ProfileChange(BaseModel):
    field: str
    operation: Literal["add", "update", "remove"]
    before: JsonValue
    after: JsonValue


class ProfilePreviewResponse(BaseModel):
    status: Literal["awaiting_confirmation", "no_changes"]
    confirmation_id: str | None
    message: str
    draft_version: uuid.UUID
    base_profile_version: int | None
    expires_at: datetime | None
    changes: list[ProfileChange]
    proposed: FormalProfileSnapshot


class ProfilePreviewResult(BaseModel):
    success: Literal[True]
    data: ProfilePreviewResponse
    error: None

class ProfileConfirmationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    draft_version: uuid.UUID
    base_profile_version: int | None = Field(ge=1, strict=True)
    base_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed: FormalProfileSnapshot
    changes: list[ProfileChange]


class ProfileConfirmationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    draft_version: uuid.UUID
    # Recognize non-pending states so the service can reject them as business conflicts.
    status: Literal["awaiting_confirmation", "processing", "completed", "cancelled"]
    created_at: datetime
    expires_at: datetime
    payload: ProfileConfirmationPayload

