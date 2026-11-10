import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, Table, create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from common.config import settings
from common.database import get_db
from common.exception_handlers import register_exception_handlers
from modules.auth.exceptions import SessionRequiredError
from modules.auth.schemas import UserResponse
from modules.auth.sessions import get_session_store
from modules.profile.exceptions import ProfileNotFoundError
from modules.profile.models import ApplicantProfile, ApplicantSkill, EducationEntry, SocialLink, WorkExperience
from modules.profile.route import router
from modules.profile.service import ApplicantProfileService


MODELS = (ApplicantProfile, WorkExperience, EducationEntry, SocialLink, ApplicantSkill)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def owned(user_id, **fields):
    return {"id": uuid.uuid4(), "user_id": user_id, "created_at": NOW, "updated_at": NOW, **fields}


def profile(user_id, name):
    return owned(
        user_id, country="US", first_name=name, last_name="Example", preferred_name=None,
        address="123 Example Street", city="Example City", state="MN", postal_code="01234",
        date_of_birth=date(2000, 1, 1), default_email="fixture@example.com",
        phone_device_type="mobile", country_phone_code="+1", phone_number="2025550100",
        phone_extension=None, authorized_to_work_us=True, requires_visa_sponsorship=False,
        sex="other", hispanic_or_latino=False, race="prefer_not_to_disclose",
        veteran_status="prefer_not_to_answer", version=1,
    )


class ProfileTests(unittest.TestCase):
    def setUp(self):
        # Exercise real repository queries without connecting to PostgreSQL or Redis.
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        with self.engine.connect() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
        metadata = MetaData()
        for model in MODELS:
            columns = []
            for column in model.__table__.c:
                column_type = column.type.copy()
                if hasattr(column_type, "collation"):
                    column_type.collation = None
                columns.append(Column(column.name, column_type, primary_key=column.primary_key, nullable=column.nullable))
            # PostgreSQL constraints were verified separately; this fixture tests reads and ownership.
            Table(model.__tablename__, metadata, *columns, schema="public")
        metadata.create_all(self.engine)
        self.user_id = uuid.uuid4()
        self.other_id = uuid.uuid4()
        self.empty_id = uuid.uuid4()
        with self.engine.begin() as connection:
            for user_id, name in ((self.user_id, "Reader"), (self.other_id, "Other"), (self.empty_id, "Empty")):
                connection.execute(insert(ApplicantProfile), profile(user_id, name))
            for user_id in (self.user_id, self.other_id):
                connection.execute(insert(WorkExperience), owned(
                    user_id, job_title="Engineer", company="Fictional Company", start_year=2022,
                    start_month=1, end_year=None, end_month=None, currently_employed=True,
                    role_description="Synthetic fixture", sort_order=0,
                ))
                connection.execute(insert(EducationEntry), owned(
                    user_id, school="Fictional University", degree="bachelor", major="Computer Science",
                    minor=None, gpa=Decimal("3.850"), education_status="graduated",
                    anticipated_graduation_year=None, anticipated_graduation_month=None,
                    graduation_year=2021, graduation_month=5, sort_order=0,
                ))
                connection.execute(insert(SocialLink), owned(
                    user_id, platform="portfolio", platform_name=None,
                    url="https://example.com/fixture", sort_order=0,
                ))
                for name, order in (("SQL", 2), ("Python", 0)):
                    connection.execute(insert(ApplicantSkill), owned(user_id, name=name, sort_order=order))
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)

        def test_db():
            with Session(self.engine) as session:
                yield session

        owner = self

        class FakeSessions:
            def get(self, token):
                if token == "reader-session":
                    return UserResponse(id=owner.user_id, username="reader")
                if token == "empty-session":
                    return UserResponse(id=owner.empty_id, username="empty")
                if token == "missing-profile-session":
                    return UserResponse(id=uuid.uuid4(), username="newuser")
                raise SessionRequiredError("Please log in again")

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_session_store] = lambda: FakeSessions()
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def login(self, token="reader-session"):
        self.client.cookies.set(settings.session_cookie_name, token)

    def test_complete_profile_filters_every_table_by_owner(self):
        with Session(self.engine) as db:
            result = ApplicantProfileService(db).obtain_complete_profile_by_user_id(self.user_id)
        self.assertEqual(result.profile.first_name, "Reader")
        for entries in (result.work_experiences, result.education_entries, result.social_links, result.skills):
            self.assertTrue(entries)
            self.assertTrue(all(entry.user_id == self.user_id for entry in entries))
        self.assertEqual(len(result.work_experiences), 1)
        self.assertEqual([skill.name for skill in result.skills], ["Python", "SQL"])
        self.assertEqual(result.education_entries[0].gpa, Decimal("3.850"))

    def test_empty_child_lists_are_successful(self):
        self.login("empty-session")
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        for field in ("work_experiences", "education_entries", "social_links", "skills"):
            self.assertEqual(data[field], [])

    def test_missing_profile_is_a_business_error(self):
        with Session(self.engine) as db:
            with self.assertRaises(ProfileNotFoundError):
                ApplicantProfileService(db).obtain_complete_profile_by_user_id(uuid.uuid4())

    def test_logged_in_user_without_profile_gets_clear_response(self):
        self.login("missing-profile-session")
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            "success": False, "data": None,
            "error": {"code": "ProfileNotFoundError", "message": "Profile not found", "retryable": False},
        })

    def test_missing_or_invalid_session_is_rejected(self):
        for token in (None, "expired-session"):
            with self.subTest(token=token):
                self.client.cookies.clear()
                if token:
                    self.login(token)
                response = self.client.get("/profile/")
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])
                self.assertIsNone(response.json()["data"])
                self.assertEqual(response.json()["error"]["code"], "SessionRequiredError")

    def test_success_envelope_serializes_uuid_date_and_decimal(self):
        self.login()
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["profile"]["user_id"], str(self.user_id))
        self.assertEqual(body["data"]["profile"]["date_of_birth"], "2000-01-01")
        self.assertEqual(body["data"]["education_entries"][0]["gpa"], "3.850")
        self.assertNotIn("password", response.text)
        self.assertNotIn("_sa_instance_state", response.text)

    def test_client_cannot_select_another_users_profile(self):
        self.login()
        response = self.client.get("/profile/", params={"user_id": str(self.other_id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["profile"]["user_id"], str(self.user_id))


if __name__ == "__main__":
    unittest.main()
