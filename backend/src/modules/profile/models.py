import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, JSON, Numeric, SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

# Reuse the account metadata so public.users foreign keys resolve without a second Base.
from modules.auth.models import Base


class ProfileConfirmationReceipt(Base):
    """Durable outcome committed atomically with the approved profile writes."""

    __tablename__ = "profile_confirmation_receipts"
    __table_args__ = ({"schema": "public"},)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id"), primary_key=True,
    )
    confirmation_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )


class ApplicantProfile(Base):
    __tablename__ = "applicant_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="applicant_profiles_user_unique"),
        CheckConstraint("country = 'US'", name="applicant_profiles_country_check"),
        CheckConstraint("first_name ~ '[^[:space:]]' AND last_name ~ '[^[:space:]]'", name="applicant_profiles_name_check"),
        CheckConstraint("address ~ '[^[:space:]]' AND city ~ '[^[:space:]]'", name="applicant_profiles_address_check"),
        CheckConstraint("state ~ '^[A-Z]{2}$'", name="applicant_profiles_state_format"),
        CheckConstraint("postal_code ~ '^[0-9]{5}(-[0-9]{4})?$'", name="applicant_profiles_postal_code_format"),
        CheckConstraint("default_email ~ '[^[:space:]]'", name="applicant_profiles_email_not_blank"),
        CheckConstraint("phone_device_type IN ('mobile', 'home', 'landline', 'other')", name="applicant_profiles_phone_device_check"),
        CheckConstraint("country_phone_code = '+1'", name="applicant_profiles_phone_country_check"),
        CheckConstraint("phone_number ~ '^[2-9][0-9]{9}$'", name="applicant_profiles_phone_number_format"),
        CheckConstraint("phone_extension IS NULL OR phone_extension ~ '^[0-9]+$'", name="applicant_profiles_phone_extension_format"),
        CheckConstraint("sex IN ('male', 'female', 'other')", name="applicant_profiles_sex_check"),
        CheckConstraint(
            "race IN ('american_indian_or_alaska_native', 'asian', 'black_or_african_american', "
            "'native_hawaiian_or_other_pacific_islander', 'white', 'two_or_more_races', "
            "'other', 'prefer_not_to_disclose')",
            name="applicant_profiles_race_check",
        ),
        CheckConstraint(
            "veteran_status IN ('not_protected_veteran', 'protected_veteran', 'prefer_not_to_answer')",
            name="applicant_profiles_veteran_status_check",
        ),
        CheckConstraint("version > 0", name="applicant_profiles_version_check"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id", name="applicant_profiles_user_fk", ondelete="NO ACTION"), nullable=False,
    )
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    default_email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone_device_type: Mapped[str] = mapped_column(String(20), nullable=False)
    country_phone_code: Mapped[str] = mapped_column(String(4), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    phone_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authorized_to_work_us: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_visa_sponsorship: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    hispanic_or_latino: Mapped[bool] = mapped_column(Boolean, nullable=False)
    race: Mapped[str] = mapped_column(String(64), nullable=False)
    veteran_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    # Defaults apply on insertion only; updates must maintain this timestamp and version.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    def __str__(self):
        return f"id:{self.id}, UserId:{self.user_id}, FirstName:{self.first_name}, LastName:{self.last_name}"
class WorkExperience(Base):
    __tablename__ = "work_experiences"
    __table_args__ = (
        CheckConstraint(
            "job_title ~ '[^[:space:]]' AND company ~ '[^[:space:]]' AND role_description ~ '[^[:space:]]'",
            name="work_experiences_text_check",
        ),
        CheckConstraint("start_year BETWEEN 1 AND 9999", name="work_experiences_start_year_check"),
        CheckConstraint("start_month BETWEEN 1 AND 12", name="work_experiences_start_month_check"),
        CheckConstraint("end_year BETWEEN 1 AND 9999", name="work_experiences_end_year_check"),
        CheckConstraint("end_month BETWEEN 1 AND 12", name="work_experiences_end_month_check"),
        # SQL comparisons alone accept NULL; enforce complete year/month pairs explicitly.
        CheckConstraint("(end_year IS NULL) = (end_month IS NULL)", name="work_experiences_end_pair_check"),
        CheckConstraint("NOT currently_employed OR (end_year IS NULL AND end_month IS NULL)", name="work_experiences_current_end_check"),
        CheckConstraint("end_year IS NULL OR (end_year, end_month) >= (start_year, start_month)", name="work_experiences_date_order_check"),
        CheckConstraint("sort_order >= 0", name="work_experiences_sort_check"),
        Index("work_experiences_user_order_idx", "user_id", "sort_order", "id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.users.id", ondelete="NO ACTION"), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    start_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    end_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    end_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    currently_employed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class EducationEntry(Base):
    __tablename__ = "education_entries"
    __table_args__ = (
        CheckConstraint("school ~ '[^[:space:]]' AND major ~ '[^[:space:]]'", name="education_entries_text_check"),
        CheckConstraint(
            "degree IN ('associate', 'bachelor', 'master', 'doctorate', 'professional_degree', "
            "'high_school_diploma', 'ged', 'certificate', 'other')",
            name="education_entries_degree_check",
        ),
        CheckConstraint("education_status IN ('currently_studying', 'graduated')", name="education_entries_status_check"),
        CheckConstraint("gpa BETWEEN 0 AND 4", name="education_entries_gpa_check"),
        CheckConstraint("anticipated_graduation_year BETWEEN 1 AND 9999", name="education_entries_expected_year_check"),
        CheckConstraint("anticipated_graduation_month BETWEEN 1 AND 12", name="education_entries_expected_month_check"),
        CheckConstraint("(anticipated_graduation_year IS NULL) = (anticipated_graduation_month IS NULL)", name="education_entries_expected_pair_check"),
        CheckConstraint("graduation_year BETWEEN 1 AND 9999", name="education_entries_graduation_year_check"),
        CheckConstraint("graduation_month BETWEEN 1 AND 12", name="education_entries_graduation_month_check"),
        CheckConstraint("(graduation_year IS NULL) = (graduation_month IS NULL)", name="education_entries_graduation_pair_check"),
        CheckConstraint(
            "education_status <> 'graduated' OR (graduation_year IS NOT NULL AND graduation_month IS NOT NULL)",
            name="education_entries_graduated_date_check",
        ),
        CheckConstraint("sort_order >= 0", name="education_entries_sort_check"),
        Index("education_entries_user_order_idx", "user_id", "sort_order", "id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.users.id", ondelete="NO ACTION"), nullable=False)
    school: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str] = mapped_column(String(32), nullable=False)
    major: Mapped[str] = mapped_column(String(200), nullable=False)
    minor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Decimal preserves GPA precision; None represents an omitted GPA, not zero.
    gpa: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    education_status: Mapped[str] = mapped_column(String(32), nullable=False)
    anticipated_graduation_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    anticipated_graduation_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    graduation_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class SocialLink(Base):
    __tablename__ = "social_links"
    __table_args__ = (
        CheckConstraint("platform IN ('linkedin', 'github', 'x', 'facebook', 'instagram', 'portfolio', 'other')", name="social_links_platform_check"),
        CheckConstraint("octet_length(url) <= 2048", name="social_links_url_length_check"),
        CheckConstraint("url ~ '^https?://[^[:space:]/?#]+([/?#][^[:space:]]*)?$'", name="social_links_url_format"),
        CheckConstraint("sort_order >= 0", name="social_links_sort_check"),
        UniqueConstraint("user_id", "platform", "url", name="social_links_user_platform_url_unique"),
        Index("social_links_user_order_idx", "user_id", "sort_order", "id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.users.id", ondelete="NO ACTION"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class ApplicantSkill(Base):
    __tablename__ = "applicant_skills"
    __table_args__ = (
        CheckConstraint("name ~ '[^[:space:]]'", name="applicant_skills_name_check"),
        CheckConstraint("sort_order >= 0", name="applicant_skills_sort_check"),
        UniqueConstraint("user_id", "name", name="applicant_skills_user_name_unique"),
        Index("applicant_skills_user_order_idx", "user_id", "sort_order", "id"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.users.id", ondelete="NO ACTION"), nullable=False)
    name: Mapped[str] = mapped_column(String(100, collation="C"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
