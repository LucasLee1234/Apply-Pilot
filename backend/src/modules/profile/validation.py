"""Formal input rules, kept separate from intentionally permissive draft schemas."""

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator


Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
LongName = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
Year = Annotated[int, Field(strict=True, ge=1, le=9999)]
Month = Annotated[int, Field(strict=True, ge=1, le=12)]
STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


class FormalFields(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank_text(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text must not be blank; use null for an optional empty field")
        return value


class FormalProfileInput(FormalFields):
    country: Literal["US"]
    first_name: Name
    last_name: Name
    preferred_name: Name | None = None
    address: Annotated[str, StringConstraints(strict=True, min_length=1)]
    city: Name
    state: Annotated[str, StringConstraints(strict=True, min_length=2, max_length=2)]
    postal_code: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]{5}(-[0-9]{4})?$")]
    date_of_birth: date
    default_email: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=254)]
    phone_device_type: Literal["mobile", "home", "landline", "other"]
    country_phone_code: Literal["+1"]
    phone_number: Annotated[str, StringConstraints(strict=True)]
    phone_extension: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20, pattern=r"^[0-9]+$")] | None = None
    authorized_to_work_us: StrictBool
    requires_visa_sponsorship: StrictBool
    sex: Literal["male", "female", "other"]
    hispanic_or_latino: StrictBool
    race: Literal[
        "american_indian_or_alaska_native", "asian", "black_or_african_american",
        "native_hawaiian_or_other_pacific_islander", "white", "two_or_more_races",
        "other", "prefer_not_to_disclose",
    ]
    veteran_status: Literal["not_protected_veteran", "protected_veteran", "prefer_not_to_answer"]

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        if value not in STATES:
            raise ValueError("Select a supported US state code")
        return value

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_birth_date(cls, value):
        if type(value) is date:
            parsed = value
        elif isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Enter a valid birth date in YYYY-MM-DD format") from exc
        else:
            raise ValueError("Enter a complete birth date in YYYY-MM-DD format")
        if parsed > date.today():
            raise ValueError("Birth date must not be in the future")
        return parsed

    @field_validator("default_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if value.count("@") != 1 or any(char.isspace() for char in value) or ".." in value:
            raise ValueError("Enter a valid email address")
        local, domain = value.split("@")
        # The initial policy accepts common ASCII mailbox syntax and dotted domains.
        if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
                or local.startswith(".") or local.endswith(".") or "." not in domain
                or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
                       for label in domain.split("."))):
            raise ValueError("Enter a valid ASCII email address with a dotted domain")
        return value

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        if not re.fullmatch(r"(?:\+1[ -]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[ -]?[0-9]{3}[ -]?[0-9]{4}", value):
            raise ValueError("Enter a 10-digit US phone number, optionally prefixed by +1")
        digits = re.sub(r"[^0-9]", "", value)
        return digits[1:] if len(digits) == 11 else digits


class FormalEntry(FormalFields):
    id: uuid.UUID
    sort_order: Annotated[int, Field(strict=True, ge=0)] = 0


class FormalWorkExperience(FormalEntry):
    job_title: LongName
    company: LongName
    start_year: Year
    start_month: Month
    end_year: Year | None = None
    end_month: Month | None = None
    currently_employed: StrictBool
    role_description: Annotated[str, StringConstraints(strict=True, min_length=1)]

    @model_validator(mode="after")
    def validate_dates(self):
        if (self.end_year is None) != (self.end_month is None):
            raise ValueError("End year and month must be provided together")
        if self.currently_employed and self.end_year is not None:
            raise ValueError("Current employment must not include an end date")
        if self.end_year is not None and (self.end_year, self.end_month) < (self.start_year, self.start_month):
            raise ValueError("End date must not precede start date")
        return self


class FormalEducationEntry(FormalEntry):
    school: LongName
    degree: Literal["associate", "bachelor", "master", "doctorate", "professional_degree",
                    "high_school_diploma", "ged", "certificate", "other"]
    major: LongName
    minor: LongName | None = None
    gpa: Decimal | None = None
    education_status: Literal["currently_studying", "graduated"]
    anticipated_graduation_year: Year | None = None
    anticipated_graduation_month: Month | None = None
    graduation_year: Year | None = None
    graduation_month: Month | None = None

    @field_validator("gpa", mode="before")
    @classmethod
    def validate_gpa(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,3})?", str(value)):
            raise ValueError("GPA must be numeric with at most three decimal places")
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Enter a valid GPA") from exc
        if not Decimal("0") <= number <= Decimal("4"):
            raise ValueError("GPA must be between 0 and 4")
        # Match NUMERIC(4,3) so equivalent values do not appear as false changes.
        return number.quantize(Decimal("0.001"))

    @model_validator(mode="after")
    def validate_dates(self):
        if (self.anticipated_graduation_year is None) != (self.anticipated_graduation_month is None):
            raise ValueError("Expected graduation year and month must be provided together")
        if (self.graduation_year is None) != (self.graduation_month is None):
            raise ValueError("Graduation year and month must be provided together")
        if self.education_status == "graduated" and self.graduation_year is None:
            raise ValueError("Graduated entries require an actual graduation year and month")
        return self


class FormalSocialLink(FormalEntry):
    platform: Literal["linkedin", "github", "x", "facebook", "instagram", "portfolio", "other"]
    platform_name: Name | None = None
    url: Annotated[str, StringConstraints(strict=True, min_length=1)]

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            if (not value.startswith(("http://", "https://")) or not parts.hostname
                    or parts.username is not None or parts.password is not None
                    or any(char.isspace() or ord(char) < 32 for char in value)
                    or len(value.encode("utf-8")) > 2048):
                raise ValueError("invalid")
            _ = parts.port
        except ValueError as exc:
            raise ValueError("Enter an HTTP/HTTPS URL without credentials, at most 2048 UTF-8 bytes") from exc
        return value


class FormalSkill(FormalEntry):
    name: Name


class FormalProfileSnapshot(FormalFields):
    profile: FormalProfileInput
    work_experiences: list[FormalWorkExperience] = Field(default_factory=list)
    education_entries: list[FormalEducationEntry] = Field(default_factory=list)
    social_links: list[FormalSocialLink] = Field(default_factory=list)
    skills: list[FormalSkill] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_duplicates(self):
        for section in ("work_experiences", "education_entries", "social_links", "skills"):
            entries = getattr(self, section)
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError(f"Duplicate record IDs in {section}")
        if len({entry.name for entry in self.skills}) != len(self.skills):
            raise ValueError("Duplicate skill names are not allowed")
        if len({(entry.platform, entry.url) for entry in self.social_links}) != len(self.social_links):
            raise ValueError("Duplicate links for the same platform are not allowed")
        return self
