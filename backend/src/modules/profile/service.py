import uuid

from sqlalchemy.orm import Session

from modules.profile.exceptions import ProfileNotFoundError, ProfileUpdateError, \
    ProfileCreateError, ApplicantSkillCreateError, WorkExperienceCreateError
from modules.profile.models import ApplicantProfile, ApplicantSkill, EducationEntry, SocialLink, WorkExperience
from modules.profile.repository import (
    ApplicantProfileRepository, ApplicantSkillRepository, EducationEntryRepository,
    SocialLinkRepository, WorkExperienceRepository,
)
from modules.profile.schemas import (
    CompleteProfileResponse, EducationEntryResponse, ProfileResponse,
    SkillResponse, SocialLinkResponse, WorkExperienceResponse,
)
from modules.profile.utils import editable_record
from modules.profile.validation import (
    FormalEducationEntry, FormalProfileInput, FormalSkill, FormalSocialLink,
    FormalWorkExperience,
)


class ApplicantProfileService:

    def __init__(self, db: Session):
        self.db = db
        self.applicant_profile_repository = ApplicantProfileRepository(db)
        self.work_experience_repository = WorkExperienceRepository(db)
        self.education_entry_repository = EducationEntryRepository(db)
        self.social_link_repository = SocialLinkRepository(db)
        self.applicant_skill_repository = ApplicantSkillRepository(db)

        self.handler = {
            "skills": {
                "add": self.add_skill_profile,
                "remove": self.remove_skill_by_id,
                "update": self.update_skill_by_id
            },
            "work_experiences": {
                "add": self.add_work_experience,
                "remove": self.remove_work_experience_by_id,
                "update": self.update_work_experience_by_id
            },
            "education_entries": {
                "add": self.add_education_entry,
                "remove": self.remove_education_entry_by_id,
                "update": self.update_education_entries_by_id
            },
            "social_links": {
                "add": self.add_social_link,
                "remove": self.remove_social_link_by_id,
                "update": self.update_social_links_by_id
            }
        }

    def obtain_profile_by_user_id(self, user_id: uuid.UUID) -> ApplicantProfile:
        user_id = uuid.UUID(str(user_id))
        profile = self.applicant_profile_repository.get_applicant_profile_by_user_id(user_id)

        if profile is None:
            raise ProfileNotFoundError("Profile not found")
        return profile

    def obtain_complete_profile_by_user_id(self, user_id: uuid.UUID) -> CompleteProfileResponse:
        # A missing profile is different from a valid profile with no child records.
        profile = self.obtain_profile_by_user_id(user_id)
        return CompleteProfileResponse(
            profile=ProfileResponse.model_validate(profile),
            work_experiences=[
                WorkExperienceResponse.model_validate(entry)
                for entry in self.work_experience_repository.get_work_experiences_by_user_id(user_id)
            ],
            education_entries=[
                EducationEntryResponse.model_validate(entry)
                for entry in self.education_entry_repository.get_education_entries_by_user_id(user_id)
            ],
            social_links=[
                SocialLinkResponse.model_validate(entry)
                for entry in self.social_link_repository.get_social_links_by_user_id(user_id)
            ],
            skills=[
                SkillResponse.model_validate(entry)
                for entry in self.applicant_skill_repository.get_skills_by_user_id(user_id)
            ],
        )

    def confirm_draft_save_applicant_information(self, changes: dict, user_id: uuid.UUID, *, commit: bool = True):
        user_id = uuid.UUID(str(user_id))
        if len(changes) == 0:
            raise ProfileNotFoundError("Nothing needs to be updated.")
        try:
            for key, body in changes.items():
                if key == "profile":
                    if body is None or len(body) == 0:
                        raise ProfileNotFoundError("Provide information to update profile")
                    if body.get("id") == "":
                        self.add_applicant_profile(body.get("data"), user_id=user_id)
                    else:
                        if body.get("data") is None or len(body.get("data")) == 0:
                            raise ProfileNotFoundError("Please provide information to update profile")
                        self.update_profile_by_profile_id(id=body.get("id"), profile=body.get("data"))
                    continue
                if key not in self.handler:
                    raise ValueError(f"unsupported：{key}")

                if body is None or len(body) == 0:
                    raise ProfileNotFoundError("Provide information to update profile")
                handlers = self.handler[key]
                for sub_key, sub_body in body.items():
                    operation = sub_key.split(":", 1)[0]
                    if operation == "add":
                        handlers["add"](sub_body, user_id=user_id)
                    elif operation == "remove":
                        handlers["remove"](sub_body)
                    else:
                        handlers["update"](id=sub_key, profile=sub_body)

            # A confirmation owns the outer transaction, including its durable receipt.
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except Exception:
            self.db.rollback()
            raise

    def update_profile_by_profile_id(self, id: uuid.UUID, profile: dict) -> int:
        id = uuid.UUID(str(id))
        current = self.applicant_profile_repository.get_applicant_profile_by_id(id)
        changes = self._validated_entry_changes(current, FormalProfileInput, profile)
        rows = self.applicant_profile_repository.change_applicant_profile_by_profile_id(profile_id=id, changes=changes)
        if rows == 0:
            raise ProfileUpdateError("Fail to update profile")
        return rows

    def update_skill_by_id(self, id: uuid.UUID, profile: dict) -> int:
        id = uuid.UUID(str(id))
        current = self.applicant_skill_repository.get_skill_by_id(id)
        changes = self._validated_entry_changes(current, FormalSkill, profile)
        rows = self.applicant_skill_repository.change_skill_by_id(id, changes)
        if rows == 0:
            raise ProfileUpdateError("Fail to update skill")
        return rows

    def update_work_experience_by_id(self, id: uuid.UUID, profile: dict) -> int:
        id = uuid.UUID(str(id))
        current = self.work_experience_repository.get_work_experience_by_id(id)
        changes = self._validated_entry_changes(current, FormalWorkExperience, profile)
        rows = self.work_experience_repository.change_work_experience_by_id(id, changes)
        if rows == 0:
            raise ProfileUpdateError("Fail to update work experience")
        return rows

    def update_education_entries_by_id(self, id: uuid.UUID, profile: dict) -> int:
        id = uuid.UUID(str(id))
        current = self.education_entry_repository.get_education_entry_by_id(id)
        changes = self._validated_entry_changes(current, FormalEducationEntry, profile)
        rows = self.education_entry_repository.change_education_entry_by_id(id, changes)
        if rows == 0:
            raise ProfileUpdateError("Fail to update education entry")
        return rows

    def update_social_links_by_id(self, id: uuid.UUID, profile: dict) -> int:
        id = uuid.UUID(str(id))
        current = self.social_link_repository.get_social_link_by_id(id)
        changes = self._validated_entry_changes(current, FormalSocialLink, profile)
        rows = self.social_link_repository.change_social_link_by_id(id, changes)
        if rows == 0:
            raise ProfileUpdateError("Fail to update social link")
        return rows

    @staticmethod
    def _validated_entry_changes(current, schema, changes: dict) -> dict:
        if current is None:
            raise ProfileNotFoundError("Record not found")
        if "id" in changes:
            raise ValueError("Record ID cannot be updated")
        # Validate partial edits against saved fields, including date-pair rules.
        formal = schema.model_validate({**editable_record(current, schema), **changes})
        return formal.model_dump(include=set(changes))

    def add_applicant_profile(self, profile, user_id: uuid.UUID) -> ApplicantProfile:
        user_id = uuid.UUID(str(user_id))
        formal_profile = FormalProfileInput.model_validate(profile)
        result = self.applicant_profile_repository.insert_applicant_profile(formal_profile, user_id=user_id)
        if result is None:
            raise ProfileCreateError("Fail to create profile")
        return result

    def add_skill_profile(self, skill, user_id: uuid.UUID) -> ApplicantSkill:
        user_id = uuid.UUID(str(user_id))
        formal_skill = FormalSkill.model_validate(skill)

        result = self.applicant_skill_repository.insert_skill(formal_skill, user_id)
        if result is None:
            raise ApplicantSkillCreateError("Fail to create skill")
        return result

    def add_work_experience(self, work_experience, user_id: uuid.UUID) -> WorkExperience:
        user_id = uuid.UUID(str(user_id))
        formal_work_experience = FormalWorkExperience.model_validate(work_experience)

        result = self.work_experience_repository.insert_work_experience(formal_work_experience, user_id=user_id)
        if result is None:
            raise WorkExperienceCreateError("Fail to create work experience")
        return result

    def add_education_entry(self, profile, user_id: uuid.UUID) -> EducationEntry:
        user_id = uuid.UUID(str(user_id))
        formal = FormalEducationEntry.model_validate(profile)
        result = self.education_entry_repository.insert_education_entry(formal, user_id=user_id)
        if result is None:
            raise ProfileCreateError("Fail to create education entry")
        return result

    def add_social_link(self, profile, user_id: uuid.UUID) -> SocialLink:
        user_id = uuid.UUID(str(user_id))
        formal = FormalSocialLink.model_validate(profile)
        result = self.social_link_repository.insert_social_link(formal, user_id=user_id)
        if result is None:
            raise ProfileCreateError("Fail to create social link")
        return result

    def remove_applicant_profile_by_id(self, id: uuid.UUID) -> int:
        rows = self.applicant_profile_repository.remove_applicant_profile_by_id(uuid.UUID(str(id)))
        if rows == 0:
            raise ProfileNotFoundError("Profile not found")
        return rows

    def remove_skill_by_id(self, id: uuid.UUID) -> int:
        rows = self.applicant_skill_repository.remove_skill_by_id(uuid.UUID(str(id)))
        if rows == 0:
            raise ProfileNotFoundError("Skill not found")
        return rows

    def remove_work_experience_by_id(self, id: uuid.UUID) -> int:
        rows = self.work_experience_repository.remove_work_experience_by_id(uuid.UUID(str(id)))
        if rows == 0:
            raise ProfileNotFoundError("Work experience not found")
        return rows

    def remove_education_entry_by_id(self, id: uuid.UUID) -> int:
        rows = self.education_entry_repository.remove_education_entry_by_id(uuid.UUID(str(id)))
        if rows == 0:
            raise ProfileNotFoundError("Education entry not found")
        return rows

    def remove_social_link_by_id(self, id: uuid.UUID) -> int:
        rows = self.social_link_repository.remove_social_link_by_id(uuid.UUID(str(id)))
        if rows == 0:
            raise ProfileNotFoundError("Social link not found")
        return rows
