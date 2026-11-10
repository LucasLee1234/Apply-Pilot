import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from modules.profile.models import ApplicantProfile
from modules.profile.repository import (
    ApplicantProfileRepository, ApplicantSkillRepository, EducationEntryRepository,
    SocialLinkRepository, WorkExperienceRepository,
)
from modules.profile.validation import (
    FormalEducationEntry, FormalProfileInput, FormalSkill, FormalSocialLink, FormalWorkExperience,
)


SECTIONS = {
    "work_experiences": (FormalWorkExperience, WorkExperienceRepository, "get_work_experiences_by_user_id"),
    "education_entries": (FormalEducationEntry, EducationEntryRepository, "get_education_entries_by_user_id"),
    "social_links": (FormalSocialLink, SocialLinkRepository, "get_social_links_by_user_id"),
    "skills": (FormalSkill, ApplicantSkillRepository, "get_skills_by_user_id"),
}


def json_value(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def editable_record(record, schema) -> dict:
    return {name: json_value(getattr(record, name)) for name in schema.model_fields}


def read_baseline(
    db: Session, user_id: uuid.UUID,
) -> tuple[ApplicantProfile | None, dict]:
    """Read the same editable fields and child ordering for preview and confirmation."""
    current = ApplicantProfileRepository(db).get_applicant_profile_by_user_id(user_id)
    baseline = {"profile": editable_record(current, FormalProfileInput) if current else {}}
    for section, (schema, repository_class, method) in SECTIONS.items():
        repository = repository_class(db)
        baseline[section] = [editable_record(row, schema) for row in getattr(repository, method)(user_id)]
    return current, baseline


def get_fingerprint(current_id: str | None, base_version: int | None, baseline: dict) -> str:
    # A missing profile binds to JSON null, not the literal string "None".
    binding = {"profile_id": current_id if current_id else None,
               "profile_version": base_version, "data": baseline}
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
