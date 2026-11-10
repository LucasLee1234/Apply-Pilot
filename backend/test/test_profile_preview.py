import json
import os
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import test_profile as fixtures
import test_profile_drafts as draft_fixtures
from common.database import get_db
from common.exception_handlers import register_exception_handlers
from modules.auth.dependencies import get_current_user
from modules.auth.exceptions import SessionRequiredError
from modules.auth.schemas import UserResponse
from modules.profile.confirmations import ProfileConfirmationStore, get_profile_confirmation_store
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore, get_profile_draft_store
from modules.profile.exceptions import DraftConflictError, ProfileValidationError, ProfileVersionConflictError
from modules.profile.models import ApplicantProfile
from modules.profile.preview import ProfilePreviewService
from modules.profile.preview_schemas import PreviewProfileRequest
from modules.profile.route import router
from modules.profile.schemas import SaveProfileDraftRequest
from modules.profile.service import ApplicantProfileService
from modules.profile.validation import (
    FormalEducationEntry, FormalProfileInput, FormalProfileSnapshot, FormalSocialLink, FormalWorkExperience,
)


def valid_profile(user_id=None):
    fields = fixtures.profile(user_id or uuid.uuid4(), "Example")
    return {key: fields[key] for key in FormalProfileInput.model_fields}


class FormalValidationTests(unittest.TestCase):
    def test_valid_profile_and_phone_normalization(self):
        value = FormalProfileInput.model_validate({**valid_profile(), "phone_number": "+1 (202) 555-0100"})
        self.assertEqual(value.phone_number, "2025550100")
        self.assertEqual(value.postal_code, "01234")

    def test_profile_business_rules(self):
        for field, value in (
            ("first_name", "  "), ("state", "ZZ"), ("country", "CA"),
            ("postal_code", "1234"), ("date_of_birth", "2000-02-30"),
            ("date_of_birth", "2000-01"), ("date_of_birth", 12345),
            ("date_of_birth", date.today() + timedelta(days=1)),
            ("default_email", "invalid"), ("default_email", "a..b@example.com"),
            ("default_email", "a@-example.com"), ("phone_number", "1025550100"),
            ("phone_extension", "abc"), ("authorized_to_work_us", "yes"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                FormalProfileInput.model_validate({**valid_profile(), field: value})

    def test_employment_date_rules(self):
        base = dict(id=uuid.uuid4(), job_title="Engineer", company="Example", start_year=2024,
                    start_month=1, currently_employed=True, role_description="Example")
        FormalWorkExperience.model_validate(base)
        for changes in (
            {"end_year": 2025}, {"end_year": 2025, "end_month": 1},
            {"currently_employed": False, "end_year": 2023, "end_month": 12},
            {"start_month": 13}, {"start_year": "2024"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                FormalWorkExperience.model_validate({**base, **changes})

    def test_optional_gpa_and_graduation_rules(self):
        base = dict(id=uuid.uuid4(), school="Example", degree="bachelor", major="CS", education_status="currently_studying")
        self.assertIsNone(FormalEducationEntry.model_validate(base).gpa)
        for value in (0, "3.850", 4):
            FormalEducationEntry.model_validate({**base, "gpa": value})
        for value in (True, "3.1234", "3e0", -1, "4.001", "not entered"):
            with self.subTest(gpa=value), self.assertRaises(ValidationError):
                FormalEducationEntry.model_validate({**base, "gpa": value})
        with self.assertRaises(ValidationError):
            FormalEducationEntry.model_validate({**base, "education_status": "graduated"})
        FormalEducationEntry.model_validate({**base, "education_status": "graduated", "graduation_year": 2024, "graduation_month": 5})

    def test_url_credentials_and_duplicate_entries(self):
        for url in ("javascript:alert(1)", "https://user:secret@example.com/", "https://example.com:bad/", "https://example.com/a b"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                FormalSocialLink(id=uuid.uuid4(), platform="portfolio", url=url)
        with self.assertRaises(ValidationError):
            FormalProfileSnapshot(profile=valid_profile(), skills=[
                {"id": uuid.uuid4(), "name": "Python"}, {"id": uuid.uuid4(), "name": "Python"},
            ])


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProfileTests("test_complete_profile_filters_every_table_by_owner")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.engine = self.fixture.engine
        self.user_id = self.fixture.user_id
        self.drafts = Mock(spec=ProfileDraftStore)
        self.raw = draft_fixtures.stored(self.user_id, {"profile": {"first_name": "Changed"}})
        self.drafts.get.return_value = self.raw
        self.confirmations = Mock(spec=ProfileConfirmationStore)
        self.confirmations.create.return_value = ("fixture-confirmation", datetime.now(timezone.utc) + timedelta(minutes=15))
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=self.user_id, username="reader")
        def db():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_profile_draft_store] = lambda: self.drafts
        app.dependency_overrides[get_profile_confirmation_store] = lambda: self.confirmations
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def request(self, **changes):
        return {"draft_version": self.raw["version"], "expected_profile_version": 1, **changes}

    def test_preview_binds_reviewed_contents_and_never_writes_sql(self):
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.split()[0].upper())
        event.listen(self.engine, "before_cursor_execute", capture)
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["status"], "awaiting_confirmation")
        self.assertEqual(data["changes"], [{"field": "profile.first_name", "operation": "update", "before": "Reader", "after": "Changed"}])
        self.assertEqual(len(data["proposed"]["work_experiences"]), 1)
        owner, version, payload = self.confirmations.create.call_args.args
        self.assertEqual(owner, self.user_id)
        self.assertEqual(str(version), self.raw["version"])
        binding = json.loads(payload)
        self.assertEqual(binding["proposed"], data["proposed"])
        self.assertEqual(binding["changes"], data["changes"])
        self.assertEqual(len(binding["base_snapshot_hash"]), 64)
        self.assertTrue(statements)
        self.assertEqual(set(statements), {"SELECT"})
        self.drafts.save.assert_not_called()

    def test_invalid_fields_return_paths_and_keep_draft(self):
        self.raw["data"] = json.dumps({"profile": {"default_email": "invalid", "date_of_birth": "unfinished"}})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 422)
        fields = {issue["field"] for issue in response.json()["error"]["details"]}
        self.assertIn("profile.default_email", fields)
        self.assertIn("profile.date_of_birth", fields)
        self.confirmations.create.assert_not_called()
        self.drafts.save.assert_not_called()

    def test_missing_and_stale_draft(self):
        response = self.client.post("/profile/preview", json=self.request(draft_version=str(uuid.uuid4())))
        self.assertEqual(response.status_code, 409)
        self.drafts.get.return_value = None
        self.assertEqual(self.client.post("/profile/preview", json=self.request()).status_code, 404)
        self.confirmations.create.assert_not_called()

    def test_stale_formal_version_is_rejected(self):
        self.assertEqual(self.client.post("/profile/preview", json=self.request(expected_profile_version=2)).status_code, 409)
        self.confirmations.create.assert_not_called()

    def saved_sections(self):
        with Session(self.engine) as db:
            return ApplicantProfileService(db).obtain_complete_profile_by_user_id(self.user_id).model_dump(mode="json")

    def test_empty_child_operations_preserve_all_saved_records(self):
        saved = self.saved_sections()
        for section in ("skills", "social_links", "work_experiences", "education_entries"):
            for operations in ([], [{}], [{"id": None}]):
                with self.subTest(section=section, operations=operations):
                    self.raw["data"] = json.dumps({section: operations})
                    response = self.client.post("/profile/preview", json=self.request())
                    self.assertEqual(response.status_code, 200, response.text)
                    data = response.json()["data"]
                    self.assertEqual(data["status"], "no_changes")
                    self.assertEqual([row["id"] for row in data["proposed"][section]],
                                     [row["id"] for row in saved[section]])
        self.confirmations.create.assert_not_called()

    def test_id_only_deletes_only_the_target_record_in_each_section(self):
        saved = self.saved_sections()
        for section in ("skills", "social_links", "work_experiences", "education_entries"):
            with self.subTest(section=section):
                target = saved[section][0]["id"]
                self.raw["data"] = json.dumps({section: [{"id": target}]})
                response = self.client.post("/profile/preview", json=self.request())
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()["data"]
                self.assertEqual([row["id"] for row in data["proposed"][section]],
                                 [row["id"] for row in saved[section] if row["id"] != target])
                self.assertEqual(len(data["changes"]), 1)
                self.assertEqual(data["changes"][0]["operation"], "remove")
                self.assertEqual(data["changes"][0]["field"], f"{section}[{target}]")

    def test_partial_update_preserves_unmentioned_records_in_each_section(self):
        saved = self.saved_sections()
        for section, field, value in (("skills", "name", "Python3"),
                                      ("social_links", "url", "https://example.com/changed"),
                                      ("work_experiences", "company", "Changed Company"),
                                      ("education_entries", "school", "Changed School")):
            with self.subTest(section=section):
                target = saved[section][0]["id"]
                self.raw["data"] = json.dumps({section: [{"id": target, field: value}]})
                response = self.client.post("/profile/preview", json=self.request())
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()["data"]
                self.assertEqual(len(data["proposed"][section]), len(saved[section]))
                self.assertEqual(data["changes"], [{"field": f"{section}[{target}].{field}",
                                                   "operation": "update", "before": saved[section][0][field], "after": value}])

    def test_new_entries_append_without_removing_saved_entries_in_each_section(self):
        saved = self.saved_sections()
        for section, field, value in (("skills", "name", "Rust"),
                                      ("social_links", "url", "https://example.com/new"),
                                      ("work_experiences", "company", "New Company"),
                                      ("education_entries", "school", "New School")):
            with self.subTest(section=section):
                entry = {key: val for key, val in saved[section][0].items()
                         if key not in ("id", "user_id", "created_at", "updated_at", "sort_order")}
                entry[field] = value
                self.raw["data"] = json.dumps({section: [entry]})
                response = self.client.post("/profile/preview", json=self.request())
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()["data"]
                self.assertEqual(len(data["proposed"][section]), len(saved[section]) + 1)
                self.assertEqual(len(data["changes"]), 1)
                self.assertEqual(data["changes"][0]["operation"], "add")
                self.assertEqual(data["proposed"][section][-1][field], value)

    def test_mixed_skill_operations_preserve_complete_proposal(self):
        skills = self.saved_sections()["skills"]
        self.raw["data"] = json.dumps({"skills": [
            {"id": skills[0]["id"], "name": "Python3"},
            {"id": skills[1]["id"]}, {"name": "Rust"}, {},
        ]})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual([row["name"] for row in data["proposed"]["skills"]], ["Python3", "Rust"])
        self.assertCountEqual([change["operation"] for change in data["changes"]], ["update", "remove", "add"])

    def test_repeated_target_ids_are_rejected_even_for_deletion(self):
        target = self.saved_sections()["skills"][0]["id"]
        for operations in ([{"id": target}, {"id": target}],
                           [{"id": target}, {"id": target, "name": "Rust"}]):
            with self.subTest(operations=operations):
                self.raw["data"] = json.dumps({"skills": operations})
                response = self.client.post("/profile/preview", json=self.request())
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["error"]["details"][0]["field"], "skills.1.id")

    def test_explicit_null_is_an_edit_not_a_delete(self):
        saved = self.saved_sections()
        target = saved["education_entries"][0]["id"]
        self.raw["data"] = json.dumps({"education_entries": [{"id": target, "gpa": None}]})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["proposed"]["education_entries"][0]["id"], target)
        self.assertIsNone(data["proposed"]["education_entries"][0]["gpa"])
        self.assertEqual(data["changes"], [{"field": f"education_entries[{target}].gpa",
                                           "operation": "update", "before": "3.850", "after": None}])

    def test_deletion_requires_a_valid_owned_id(self):
        for target in ("", "invalid-uuid", str(uuid.uuid4())):
            with self.subTest(target=target):
                self.raw["data"] = json.dumps({"skills": [{"id": target}]})
                response = self.client.post("/profile/preview", json=self.request())
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["error"]["details"][0]["field"], "skills.0.id")
        self.confirmations.create.assert_not_called()

    def test_foreign_child_ids_cannot_be_rebound(self):
        self.raw["data"] = json.dumps({"skills": [{"id": str(uuid.uuid4()), "name": "Foreign"}]})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["details"][0]["field"], "skills.0.id")
        self.confirmations.create.assert_not_called()

    def test_new_child_id_is_frozen_in_preview(self):
        self.raw["data"] = json.dumps({"skills": [{"name": "Rust"}]})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        new_id = response.json()["data"]["proposed"]["skills"][-1]["id"]
        self.assertIsInstance(uuid.UUID(new_id), uuid.UUID)
        self.assertEqual(json.loads(self.confirmations.create.call_args.args[2])["proposed"]["skills"][-1]["id"], new_id)

    def test_no_changes_requires_no_confirmation(self):
        self.raw["data"] = "{}"
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "no_changes")
        self.assertIsNone(response.json()["data"]["confirmation_id"])
        self.confirmations.create.assert_not_called()

    def test_equivalent_gpa_does_not_propose_a_change(self):
        with Session(self.engine) as db:
            entry = ApplicantProfileService(db).obtain_complete_profile_by_user_id(self.user_id).education_entries[0]
        self.raw["data"] = json.dumps({"education_entries": [{"id": str(entry.id), "gpa": "3.85"}]})
        response = self.client.post("/profile/preview", json=self.request())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "no_changes")

    def test_first_profile_requires_complete_fields(self):
        self.user_id = uuid.uuid4()
        self.raw.update(user_id=str(self.user_id), data=json.dumps({"profile": {"first_name": "New"}}))
        response = self.client.post("/profile/preview", json=self.request(expected_profile_version=None))
        self.assertEqual(response.status_code, 422)
        self.raw["data"] = json.dumps({"profile": jsonable_encoder(valid_profile(self.user_id))})
        response = self.client.post("/profile/preview", json=self.request(expected_profile_version=None))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["data"]["base_profile_version"])

    def test_unauthenticated_preview_is_rejected(self):
        def reject():
            raise SessionRequiredError("Please log in again")
        self.app.dependency_overrides[get_current_user] = reject
        response = self.client.post("/profile/preview", json=self.request())
        self.assertFalse(response.json()["success"])
        self.drafts.get.assert_not_called()
        self.confirmations.create.assert_not_called()

    def test_draft_change_during_preview_returns_conflict(self):
        self.confirmations.create.side_effect = DraftConflictError("Draft changed or expired")
        self.assertEqual(self.client.post("/profile/preview", json=self.request()).status_code, 409)


@unittest.skipUnless(os.environ.get("PROFILE_DRAFT_REDIS_TEST_URL"), "Optional live Redis integration")
class ConfirmationRedisTests(unittest.TestCase):
    def setUp(self):
        self.redis = Redis.from_url(os.environ["PROFILE_DRAFT_REDIS_TEST_URL"], decode_responses=True,
                                    socket_connect_timeout=3, socket_timeout=3)
        self.addCleanup(self.redis.close)
        self.user_id = uuid.uuid4()
        self.draft_key = ProfileDraftStore.prefix + str(self.user_id)
        self.addCleanup(self.redis.delete, self.draft_key)
        self.confirmation_keys = []
        self.addCleanup(lambda: self.redis.delete(*self.confirmation_keys) if self.confirmation_keys else None)
        self.drafts = ProfileDraftService(ProfileDraftStore(self.redis))
        self.confirmations = ProfileConfirmationStore(self.redis)
        self.draft = self.drafts.save_draft(self.user_id, SaveProfileDraftRequest(expected_version=None, data={}))

    def create(self, version=None, payload='{"proposed": {"skills": []}}'):
        token, expiry = self.confirmations.create(self.user_id, version or self.draft.version, payload)
        self.confirmation_keys.append(ProfileConfirmationStore.prefix + str(self.user_id) + ":" + token)
        return token, expiry

    def test_pending_confirmation_retains_exact_payload_and_owner(self):
        payload = '{"proposed":{"skills":[]},"large":123456789012345678901234567890}'
        token, expiry = self.create(payload=payload)
        key = self.confirmation_keys[-1]
        self.assertEqual(self.redis.hget(key, "payload"), payload)
        self.assertEqual(self.redis.hget(key, "status"), "awaiting_confirmation")
        self.assertEqual(self.redis.hget(key, "user_id"), str(self.user_id))
        self.assertEqual(self.redis.hget(key, "draft_version"), str(self.draft.version))
        self.assertGreater(len(token), 40)
        self.assertGreater(self.redis.ttl(key), 890)
        self.assertLessEqual(self.redis.ttl(key), 900)
        self.assertFalse(self.redis.exists(ProfileConfirmationStore.prefix + str(uuid.uuid4()) + ":" + token))

    def test_pending_lifetime_cannot_outlast_the_draft(self):
        self.redis.expire(self.draft_key, 30)
        self.create()
        self.assertGreater(self.redis.ttl(self.confirmation_keys[-1]), 0)
        self.assertLessEqual(self.redis.ttl(self.confirmation_keys[-1]), self.redis.ttl(self.draft_key))

    def test_changed_draft_cannot_generate_confirmation_for_old_contents(self):
        self.drafts.save_draft(self.user_id, SaveProfileDraftRequest(expected_version=self.draft.version, data={"skills": []}))
        with self.assertRaises(DraftConflictError):
            self.create()


if __name__ == "__main__":
    unittest.main()
