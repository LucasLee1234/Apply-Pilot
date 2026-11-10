import datetime
import uuid

from sqlalchemy import select, update, insert, delete
from sqlalchemy.orm import Session

from modules.profile.models import (
    ApplicantProfile, ApplicantSkill, EducationEntry, SocialLink, WorkExperience,
)
from modules.profile.validation import (
    FormalEducationEntry, FormalProfileInput, FormalSkill, FormalSocialLink,
    FormalWorkExperience,
)
from modules.profile.exceptions import ProfileVersionConflictError


class ApplicantProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def bump_version(self, user_id: uuid.UUID, expected_version: int):
        result = self.db.execute(update(ApplicantProfile).where(
            ApplicantProfile.user_id == user_id, ApplicantProfile.version == expected_version,
        ).values(version=ApplicantProfile.version + 1, updated_at=datetime.datetime.now(datetime.timezone.utc)))
        if result.rowcount != 1:
            raise ProfileVersionConflictError("Formal profile changed. Preview again.")

    def get_applicant_profile_by_user_id(self, user_id: uuid.UUID) -> ApplicantProfile | None:
        # Baseline checks must refresh existing identity-map entries before comparing versions.
        stmt = select(ApplicantProfile).where(ApplicantProfile.user_id == user_id).execution_options(populate_existing=True)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_applicant_profile_by_id(self, id: uuid.UUID) -> ApplicantProfile | None:
        stmt = select(ApplicantProfile).where(ApplicantProfile.id == id).execution_options(populate_existing=True)
        return self.db.execute(stmt).scalar_one_or_none()

    def change_applicant_profile_by_profile_id(self, profile_id: uuid.UUID, changes: dict) -> int:
        updated_at = datetime.datetime.now(datetime.timezone.utc)
        result = self.db.execute(
            update(ApplicantProfile).where(ApplicantProfile.id == profile_id).values(**changes, updated_at=updated_at, version=ApplicantProfile.version + 1)
        )
        return result.rowcount

    def insert_applicant_profile(self, profile: FormalProfileInput, user_id: uuid.UUID) -> ApplicantProfile:
        result = self.db.execute(
            insert(ApplicantProfile).values(**profile.model_dump(exclude_unset=True), user_id= user_id).returning(ApplicantProfile)
        )
        return result.scalar_one_or_none()

    def remove_applicant_profile_by_id(self, profile_id: uuid.UUID) -> int:
        result = self.db.execute(delete(ApplicantProfile).where(ApplicantProfile.id == profile_id))
        return result.rowcount


class WorkExperienceRepository:
    def __init__(self, db: Session):
        self.db = db

    # Every query is scoped to the authenticated owner; stable ordering preserves UI order.
    def get_work_experiences_by_user_id(self, user_id: uuid.UUID) -> list[WorkExperience]:
        stmt = select(WorkExperience).where(WorkExperience.user_id == user_id).order_by(
            WorkExperience.sort_order, WorkExperience.id,
        )
        return list(self.db.execute(stmt.execution_options(populate_existing=True)).scalars().all())

    def insert_work_experience(self, work_experience: FormalWorkExperience, user_id: uuid.UUID) -> WorkExperience:
        result = self.db.execute(
            insert(WorkExperience).values(**work_experience.model_dump(exclude_unset=True), user_id=user_id).returning(WorkExperience)
        )

        return result.scalar_one_or_none()

    def get_work_experience_by_id(self, id: uuid.UUID) -> WorkExperience | None:
        stmt = select(WorkExperience).where(WorkExperience.id == id).execution_options(populate_existing=True)
        return self.db.execute(stmt).scalar_one_or_none()

    def change_work_experience_by_id(self, id: uuid.UUID, changes: dict) -> int:
        result = self.db.execute(
            update(WorkExperience).where(WorkExperience.id == id).values(
                **changes, updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        return result.rowcount

    def remove_work_experience_by_id(self, id: uuid.UUID) -> int:
        result = self.db.execute(delete(WorkExperience).where(WorkExperience.id == id))
        return result.rowcount


class EducationEntryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_education_entries_by_user_id(self, user_id: uuid.UUID) -> list[EducationEntry]:
        stmt = select(EducationEntry).where(EducationEntry.user_id == user_id).order_by(
            EducationEntry.sort_order, EducationEntry.id,
        )
        return list(self.db.execute(stmt.execution_options(populate_existing=True)).scalars().all())

    def insert_education_entry(self, education: FormalEducationEntry, user_id: uuid.UUID) -> EducationEntry:
        result = self.db.execute(
            insert(EducationEntry).values(
                **education.model_dump(exclude_unset=True), user_id=user_id,
            ).returning(EducationEntry)
        )
        return result.scalar_one_or_none()

    def get_education_entry_by_id(self, id: uuid.UUID) -> EducationEntry | None:
        stmt = select(EducationEntry).where(EducationEntry.id == id).execution_options(populate_existing=True)
        return self.db.execute(stmt).scalar_one_or_none()

    def change_education_entry_by_id(self, id: uuid.UUID, changes: dict) -> int:
        result = self.db.execute(
            update(EducationEntry).where(EducationEntry.id == id).values(
                **changes, updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        return result.rowcount

    def remove_education_entry_by_id(self, id: uuid.UUID) -> int:
        result = self.db.execute(delete(EducationEntry).where(EducationEntry.id == id))
        return result.rowcount


class SocialLinkRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_social_links_by_user_id(self, user_id: uuid.UUID) -> list[SocialLink]:
        stmt = select(SocialLink).where(SocialLink.user_id == user_id).order_by(
            SocialLink.sort_order, SocialLink.id,
        )
        return list(self.db.execute(stmt.execution_options(populate_existing=True)).scalars().all())

    def insert_social_link(self, link: FormalSocialLink, user_id: uuid.UUID) -> SocialLink:
        result = self.db.execute(
            insert(SocialLink).values(
                **link.model_dump(exclude_unset=True), user_id=user_id,
            ).returning(SocialLink)
        )
        return result.scalar_one_or_none()

    def get_social_link_by_id(self, id: uuid.UUID) -> SocialLink | None:
        stmt = select(SocialLink).where(SocialLink.id == id).execution_options(populate_existing=True)
        return self.db.execute(stmt).scalar_one_or_none()

    def change_social_link_by_id(self, id: uuid.UUID, changes: dict) -> int:
        result = self.db.execute(
            update(SocialLink).where(SocialLink.id == id).values(
                **changes, updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        return result.rowcount

    def remove_social_link_by_id(self, id: uuid.UUID) -> int:
        result = self.db.execute(delete(SocialLink).where(SocialLink.id == id))
        return result.rowcount


class ApplicantSkillRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_skills_by_user_id(self, user_id: uuid.UUID) -> list[ApplicantSkill]:
        stmt = select(ApplicantSkill).where(ApplicantSkill.user_id == user_id).order_by(
            ApplicantSkill.sort_order, ApplicantSkill.id,
        )
        return list(self.db.execute(stmt.execution_options(populate_existing=True)).scalars().all())
    def insert_skill(self, skill: FormalSkill, user_id: uuid.UUID) -> ApplicantSkill:
        result = self.db.execute(
            insert(ApplicantSkill).values(**skill.model_dump(exclude_unset=True), user_id=user_id).returning(ApplicantSkill)
        )
        return result.scalar_one_or_none()

    def get_skill_by_id(self, id: uuid.UUID) -> ApplicantSkill | None:
        stmt = select(ApplicantSkill).where(ApplicantSkill.id == id).execution_options(populate_existing=True)
        return self.db.execute(stmt).scalar_one_or_none()

    def change_skill_by_id(self, id: uuid.UUID, changes: dict) -> int:
        result = self.db.execute(
            update(ApplicantSkill).where(ApplicantSkill.id == id).values(
                **changes, updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        return result.rowcount

    def remove_skill_by_id(self, id: uuid.UUID) -> int:
        result = self.db.execute(delete(ApplicantSkill).where(ApplicantSkill.id == id))
        return result.rowcount
