import json
import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from common.config import settings
from common.exception_handlers import register_exception_handlers
from modules.auth.dependencies import get_current_user
from modules.auth.exceptions import SessionRequiredError
from modules.auth.schemas import UserResponse
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore, get_profile_draft_store
from modules.profile.exceptions import DraftConflictError, DraftStorageError, DraftTooLargeError
from modules.profile.route import router
from modules.profile.schemas import SaveProfileDraftRequest


DATA = {
    "profile": {"first_name": "Example", "date_of_birth": "unfinished", "default_email": "not an email"},
    "education_entries": [{"gpa": "not decided"}],
    "work_experiences": [], "skills": [],
}


def stored(user_id, data=DATA):
    return {
        "user_id": str(user_id), "version": str(uuid.uuid4()),
        "created_at": "1790000000", "updated_at": "1790000000", "expires_at": "1790604800",
        "data": json.dumps(data),
    }


class DraftSchemaTests(unittest.TestCase):
    def test_invalid_business_values_remain_unchanged(self):
        request = SaveProfileDraftRequest(expected_version=None, data=DATA)
        self.assertEqual(request.data.model_dump(exclude_unset=True), DATA)

    def test_empty_snapshot_and_explicit_null_are_allowed(self):
        for data in ({}, {"profile": {"phone_number": None}}, {"education_entries": []}):
            request = SaveProfileDraftRequest(expected_version=None, data=data)
            self.assertEqual(json.loads(request.data.model_dump_json(exclude_unset=True)), data)

    def test_credentials_unknown_fields_and_owner_overrides_are_rejected(self):
        for data in (
            {"password": "secret"}, {"profile": {"password": "secret"}},
            {"profile": {"user_id": str(uuid.uuid4())}},
            {"education_entries": [{"verification_code": "1234"}]},
            {"social_links": [{"username": "secret"}]},
        ):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                SaveProfileDraftRequest(expected_version=None, data=data)

    def test_expected_version_is_required(self):
        with self.assertRaises(ValidationError):
            SaveProfileDraftRequest(data={})

    def test_numbers_strings_and_booleans_are_not_coerced(self):
        data = {"profile": {"postal_code": "00123", "authorized_to_work_us": "maybe"},
                "work_experiences": [{"start_year": 2026, "currently_employed": False}]}
        request = SaveProfileDraftRequest(expected_version=None, data=data)
        self.assertEqual(request.data.model_dump(exclude_unset=True), data)


class DraftServiceTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.store = Mock(spec=ProfileDraftStore)
        self.service = ProfileDraftService(self.store)

    def test_missing_draft_returns_none(self):
        self.store.get.return_value = None
        self.assertIsNone(self.service.get_draft(self.user_id))

    def test_save_preserves_exact_snapshot(self):
        self.store.save.return_value = stored(self.user_id)
        request = SaveProfileDraftRequest(expected_version=None, data=DATA)
        result = self.service.save_draft(self.user_id, request)
        args = self.store.save.call_args.args
        self.assertEqual(args[:2], (self.user_id, None))
        self.assertEqual(json.loads(args[2]), DATA)
        self.assertEqual(result.data.model_dump(exclude_unset=True), DATA)
        self.assertEqual((result.expires_at - result.created_at).total_seconds(), 604800)

    def test_payload_limit_prevents_storage(self):
        with patch.object(settings, "profile_draft_max_bytes", 10):
            with self.assertRaises(DraftTooLargeError):
                self.service.save_draft(self.user_id, SaveProfileDraftRequest(expected_version=None, data=DATA))
        self.store.save.assert_not_called()

    def test_corrupt_or_foreign_drafts_do_not_leak(self):
        for value in (stored(uuid.uuid4()), {"user_id": str(self.user_id)}, stored(self.user_id, {"password": "secret"})):
            self.store.get.return_value = value
            with self.assertRaises(DraftStorageError):
                self.service.get_draft(self.user_id)

    def test_redis_failures_are_business_errors(self):
        redis = Mock()
        redis.hgetall.side_effect = RedisConnectionError("private connection details")
        redis.eval.side_effect = RedisConnectionError("private connection details")
        store = ProfileDraftStore(redis)
        with self.assertRaises(DraftStorageError):
            store.get(self.user_id)
        with self.assertRaises(DraftStorageError):
            store.save(self.user_id, None, "{}")


class DraftApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)
        self.user_id = uuid.uuid4()
        self.store = Mock(spec=ProfileDraftStore)
        self.store.get.return_value = None
        self.store.save.return_value = stored(self.user_id)
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=self.user_id, username="fixture")
        app.dependency_overrides[get_profile_draft_store] = lambda: self.store
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_no_draft_is_success_with_null_data(self):
        self.assertEqual(self.client.get("/profile/draft").json(), {"success": True, "data": None, "error": None})

    def test_put_and_get_use_session_owner_and_preserve_incomplete_fields(self):
        response = self.client.put("/profile/draft", json={"expected_version": None, "data": DATA})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["data"], DATA)
        self.assertEqual(body["data"]["user_id"], str(self.user_id))
        self.assertEqual(self.store.save.call_args.args[0], self.user_id)
        self.store.get.return_value = self.store.save.return_value
        response = self.client.get("/profile/draft", params={"user_id": str(uuid.uuid4())})
        self.assertEqual(response.json()["data"]["data"], DATA)
        self.store.get.assert_called_once_with(self.user_id)

    def test_unlogged_requests_are_rejected_without_storage_access(self):
        def reject():
            raise SessionRequiredError("Please log in again")
        self.app.dependency_overrides[get_current_user] = reject
        for method in ("get", "put"):
            response = getattr(self.client, method)("/profile/draft")
            self.assertFalse(response.json()["success"])
        self.store.get.assert_not_called()
        self.store.save.assert_not_called()

    def test_conflict_returns_409_without_overwrite(self):
        self.store.save.side_effect = DraftConflictError("Draft changed or expired. Reload it before saving again.")
        response = self.client.put("/profile/draft", json={"expected_version": str(uuid.uuid4()), "data": DATA})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "DRAFT_VERSION_CONFLICT")
        self.assertFalse(response.json()["error"]["retryable"])

    def test_storage_failure_returns_retryable_503(self):
        self.store.get.side_effect = DraftStorageError("Draft storage is unavailable. Please try again later.")
        response = self.client.get("/profile/draft")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["error"]["retryable"])

    def test_rejected_fields_never_reach_storage_or_echo_secrets(self):
        secret = "not-for-storage"
        response = self.client.put("/profile/draft", json={"expected_version": None, "data": {"profile": {"password": secret}}})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        self.store.save.assert_not_called()


@unittest.skipUnless(os.environ.get("PROFILE_DRAFT_REDIS_TEST_URL"), "Optional live Redis integration")
class RedisDraftIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.redis = Redis.from_url(os.environ["PROFILE_DRAFT_REDIS_TEST_URL"], decode_responses=True,
                                    socket_connect_timeout=3, socket_timeout=3)
        self.addCleanup(self.redis.close)
        self.user_id = uuid.uuid4()
        self.key = ProfileDraftStore.prefix + str(self.user_id)
        self.addCleanup(self.redis.delete, self.key)
        self.store = ProfileDraftStore(self.redis, ttl_seconds=60)
        self.service = ProfileDraftService(self.store)

    def save(self, version=None, data=DATA):
        return self.service.save_draft(self.user_id, SaveProfileDraftRequest(expected_version=version, data=data))

    def test_round_trip_invalid_values_empty_arrays_and_large_numbers(self):
        data = {**DATA, "work_experiences": [{"start_year": 123456789012345678901234567890}]}
        first = self.save(data=data)
        self.assertEqual(self.service.get_draft(self.user_id).data.model_dump(exclude_unset=True), data)
        second = self.save(first.version, {"profile": {"phone_number": None}})
        self.assertNotEqual(second.version, first.version)
        self.assertEqual(second.data.model_dump(exclude_unset=True), {"profile": {"phone_number": None}})

    def test_stale_version_cannot_overwrite(self):
        first = self.save()
        second = self.save(first.version, {})
        for expected in (None, first.version):
            with self.assertRaises(DraftConflictError):
                self.save(expected)
        self.assertEqual(self.service.get_draft(self.user_id).version, second.version)

    def test_reads_and_updates_do_not_extend_expiry(self):
        first = self.save()
        self.redis.pexpire(self.key, 30000)
        before = self.redis.pttl(self.key)
        read = self.service.get_draft(self.user_id)
        second = self.save(read.version, {})
        self.assertLessEqual(self.redis.pttl(self.key), before)
        self.assertEqual(second.created_at, first.created_at)
        self.assertEqual(second.expires_at, first.expires_at)

    def test_expired_version_cannot_overwrite_a_new_draft(self):
        first = self.save()
        self.redis.pexpire(self.key, 1)
        time.sleep(0.03)
        self.assertIsNone(self.service.get_draft(self.user_id))
        with self.assertRaises(DraftConflictError):
            self.save(first.version)
        second = self.save()
        with self.assertRaises(DraftConflictError):
            self.save(first.version)
        self.assertEqual(self.service.get_draft(self.user_id).version, second.version)

    def test_simultaneous_updates_have_exactly_one_winner(self):
        first = self.save()
        def attempt(name):
            try:
                self.save(first.version, {"profile": {"first_name": name}})
                return True
            except DraftConflictError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(attempt, ["First", "Second"]))
        self.assertEqual(sorted(outcomes), [False, True])

    def test_ownership_and_default_seven_day_retention(self):
        # Short retention is used for the other fixtures; verify the real default separately.
        store = ProfileDraftStore(self.redis)
        service = ProfileDraftService(store)
        result = service.save_draft(self.user_id, SaveProfileDraftRequest(expected_version=None, data=DATA))
        self.assertEqual((result.expires_at - result.created_at).total_seconds(), settings.profile_draft_ttl_seconds)
        self.assertGreater(self.redis.ttl(self.key), settings.profile_draft_ttl_seconds - 5)
        self.assertIsNone(service.get_draft(uuid.uuid4()))


if __name__ == "__main__":
    unittest.main()
