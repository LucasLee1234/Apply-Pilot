import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from modules.profile.preview_schemas import ProfileChange
from modules.profile.validation import FormalProfileSnapshot


class OwnedRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime



class ProfileResponse(OwnedRecordResponse):
    country: str
    first_name: str
    last_name: str
    preferred_name: str | None
    address: str
    city: str
    state: str
    postal_code: str
    date_of_birth: date
    default_email: str
    phone_device_type: str
    country_phone_code: str
    phone_number: str
    phone_extension: str | None
    authorized_to_work_us: bool
    requires_visa_sponsorship: bool
    sex: str
    hispanic_or_latino: bool
    race: str
    veteran_status: str
    version: int


class WorkExperienceResponse(OwnedRecordResponse):
    job_title: str
    company: str
    start_year: int
    start_month: int
    end_year: int | None
    end_month: int | None
    currently_employed: bool
    role_description: str
    sort_order: int


class EducationEntryResponse(OwnedRecordResponse):
    school: str
    degree: str
    major: str
    minor: str | None
    gpa: Decimal | None
    education_status: str
    anticipated_graduation_year: int | None
    anticipated_graduation_month: int | None
    graduation_year: int | None
    graduation_month: int | None
    sort_order: int


class SocialLinkResponse(OwnedRecordResponse):
    platform: str
    platform_name: str | None
    url: str
    sort_order: int


class SkillResponse(OwnedRecordResponse):
    name: str
    sort_order: int


class CompleteProfileResponse(BaseModel):
    profile: ProfileResponse
    work_experiences: list[WorkExperienceResponse] = Field(default_factory=list)
    education_entries: list[EducationEntryResponse] = Field(default_factory=list)
    social_links: list[SocialLinkResponse] = Field(default_factory=list)
    skills: list[SkillResponse] = Field(default_factory=list)


class CompleteProfileResult(BaseModel):
    success: Literal[True]
    data: CompleteProfileResponse
    error: None


# Draft fields retain invalid scalar input without coercion or formal validation.
DraftValue = StrictStr | StrictInt | StrictFloat | StrictBool | None


class DraftFields(BaseModel):
    # Reject unknown keys, including credentials and client-supplied ownership metadata.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ProfileDraftFields(DraftFields):
    country: DraftValue = None
    first_name: DraftValue = None
    last_name: DraftValue = None
    preferred_name: DraftValue = None
    address: DraftValue = None
    city: DraftValue = None
    state: DraftValue = None
    postal_code: DraftValue = None
    date_of_birth: DraftValue = None
    default_email: DraftValue = None
    phone_device_type: DraftValue = None
    country_phone_code: DraftValue = None
    phone_number: DraftValue = None
    phone_extension: DraftValue = None
    authorized_to_work_us: DraftValue = None
    requires_visa_sponsorship: DraftValue = None
    sex: DraftValue = None
    hispanic_or_latino: DraftValue = None
    race: DraftValue = None
    veteran_status: DraftValue = None


class WorkExperienceDraftFields(DraftFields):
    id: DraftValue = None
    job_title: DraftValue = None
    company: DraftValue = None
    start_year: DraftValue = None
    start_month: DraftValue = None
    end_year: DraftValue = None
    end_month: DraftValue = None
    currently_employed: DraftValue = None
    role_description: DraftValue = None
    sort_order: DraftValue = None


class EducationDraftFields(DraftFields):
    id: DraftValue = None
    school: DraftValue = None
    degree: DraftValue = None
    major: DraftValue = None
    minor: DraftValue = None
    gpa: DraftValue = None
    education_status: DraftValue = None
    anticipated_graduation_year: DraftValue = None
    anticipated_graduation_month: DraftValue = None
    graduation_year: DraftValue = None
    graduation_month: DraftValue = None
    sort_order: DraftValue = None


class SocialLinkDraftFields(DraftFields):
    id: DraftValue = None
    platform: DraftValue = None
    platform_name: DraftValue = None
    url: DraftValue = None
    sort_order: DraftValue = None


class SkillDraftFields(DraftFields):
    id: DraftValue = None
    name: DraftValue = None
    sort_order: DraftValue = None


class ProfileDraftData(DraftFields):
    profile: ProfileDraftFields = Field(default_factory=ProfileDraftFields)
    work_experiences: list[WorkExperienceDraftFields] = Field(default_factory=list)
    education_entries: list[EducationDraftFields] = Field(default_factory=list)
    social_links: list[SocialLinkDraftFields] = Field(default_factory=list)
    skills: list[SkillDraftFields] = Field(default_factory=list)


class SaveProfileDraftRequest(DraftFields):
    # Null creates a draft only when absent. Existing drafts require their exact version.
    expected_version: uuid.UUID | None
    data: ProfileDraftData


class ProfileDraftResponse(BaseModel):
    user_id: uuid.UUID
    version: uuid.UUID
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    data: ProfileDraftData


class ProfileDraftResult(BaseModel):
    success: Literal[True]
    data: ProfileDraftResponse | None
    error: None

