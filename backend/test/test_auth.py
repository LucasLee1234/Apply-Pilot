import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from common.database import get_db
from common.config import settings
from common.exception_handlers import register_exception_handlers
from modules.auth.exceptions import LoginFailedError, SessionRequiredError, UserExistsError
from modules.auth.models import Users
from modules.auth.route import router
from modules.auth.schemas import LoginRequest, UserRegister, UserResponse
from modules.auth.security import hash_password, verify_password
from modules.auth.service import UserService
from modules.auth.sessions import SessionStore, get_session_store


PASSWORD = "Example123!"


def registration(username="Alice", password=PASSWORD, **overrides):
    return UserRegister(**{
        "username": username, "password": password, "confirm_password": password, **overrides,
    })


class SchemaTests(unittest.TestCase):
    def test_boundaries_and_exact_password(self):
        for username in ("A", "A" * 20):
            for password in ("Abcdefgh1!", "A1!" + "x" * 27):
                self.assertEqual(registration(username, password).password, password)
                LoginRequest(username=username, password=password)

    def test_rejected_inputs_and_confirmation(self):
        for username in ("", "A" * 21, "bad name", "中文", "abc\n"):
            with self.subTest(username=username), self.assertRaises(ValidationError):
                registration(username)
        for password in ("Abcdefg1!", "A1!" + "x" * 28, "abcdefghij", "ABCDEFGHI!", "123456789!", "Abcdefg1! ", "Abcdefg1!中"):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                registration(password=password)
        with self.assertRaises(ValidationError):
            registration(confirm_password="Different123!")
        with self.assertRaises(ValidationError):
            UserRegister(username="Alice", password=PASSWORD)

    def test_model_matches_postgres_schema_and_hides_hash(self):
        ddl = str(CreateTable(Users.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn('public.users', ddl)
        self.assertIn('users_username_key', ddl)
        self.assertNotIn('UNIQUE (password_hash)', ddl)
        self.assertNotIn('secret-hash', str(Users(username="Alice", password_hash="secret-hash")))


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoded = hash_password(PASSWORD)

    def setUp(self):
        self.db = Mock()
        self.service = UserService(self.db)
        self.repository = self.service.user_repository = Mock()
        self.user = SimpleNamespace(id=uuid.uuid4(), username="Alice", password_hash=self.encoded)

    def test_argon2_and_valid_login(self):
        self.assertTrue(self.encoded.startswith("$argon2id$"))
        self.assertTrue(verify_password(PASSWORD, self.encoded))
        self.repository.get_user_by_username.return_value = self.user
        self.assertEqual(self.service.login_user("Alice", PASSWORD).id, self.user.id)

    def test_unknown_user_and_wrong_password_have_same_error(self):
        for user in (None, self.user):
            self.repository.get_user_by_username.return_value = user
            with self.assertRaisesRegex(LoginFailedError, "^Login failed$"):
                self.service.login_user("Alice", "Wrongpass1!")

    def test_registration_commits_only_a_hash(self):
        self.repository.get_user_by_username.return_value = None
        self.repository.create_user_by_username_password.return_value = self.user
        self.service.register_user(registration())
        values = self.repository.create_user_by_username_password.call_args.kwargs
        self.assertNotIn("confirm_password", values)
        self.assertNotEqual(values["password_hash"], PASSWORD)
        self.assertTrue(verify_password(PASSWORD, values["password_hash"]))
        self.db.commit.assert_called_once()

    def test_concurrent_duplicate_rolls_back_and_maps_constraint(self):
        self.repository.get_user_by_username.return_value = None
        original = Exception("duplicate")
        original.diag = SimpleNamespace(constraint_name="users_username_key")
        self.repository.create_user_by_username_password.side_effect = IntegrityError("insert", {}, original)
        with self.assertRaisesRegex(UserExistsError, "^Username already exists$"):
            self.service.register_user(registration())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_unrelated_integrity_errors_are_not_duplicates(self):
        self.repository.get_user_by_username.return_value = None
        error = IntegrityError("insert", {}, Exception("other constraint"))
        self.repository.create_user_by_username_password.side_effect = error
        with self.assertRaises(IntegrityError):
            self.service.register_user(registration())
        self.db.rollback.assert_called_once()


class ApiTests(unittest.TestCase):
    def setUp(self):
        # Dependency overrides prevent all database and Redis network access in these tests.
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)
        self.sessions = Mock()
        self.sessions.create.return_value = "opaque-session-token"
        app.dependency_overrides[get_db] = lambda: Mock()
        app.dependency_overrides[get_session_store] = lambda: self.sessions
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.account = UserResponse(id=uuid.uuid4(), username="Alice")
        self.service_patch = patch("modules.auth.route.UserService")
        self.service = self.service_patch.start().return_value
        self.addCleanup(self.service_patch.stop)

    def test_login_sets_cookie_without_exposing_credentials(self):
        self.service.login_user.return_value = self.account
        response = self.client.post("/auth/login", json={"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "data": {"id": str(self.account.id), "username": "Alice"}, "error": None})
        self.assertNotIn(PASSWORD, response.text)
        self.assertNotIn("opaque-session-token", response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Path=/", cookie)

    def test_session_bootstrap_returns_cookie_owner_without_credentials(self):
        self.client.cookies.set(settings.session_cookie_name, "opaque-session-token")
        self.sessions.get.return_value = self.account
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["data"], {
            "id": str(self.account.id), "username": self.account.username,
        })
        self.sessions.get.assert_called_once_with("opaque-session-token")
        self.assertNotIn("opaque-session-token", response.text)

    def test_session_bootstrap_returns_null_for_missing_expired_or_replaced_session(self):
        self.sessions.get.side_effect = SessionRequiredError("Please log in again")
        for token in (None, "expired", "replaced"):
            with self.subTest(token=token):
                self.client.cookies.clear()
                if token:
                    self.client.cookies.set(settings.session_cookie_name, token)
                response = self.client.get("/auth/me")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"success": True, "data": None, "error": None})
                self.sessions.get.assert_called_with(token)

    def test_session_bootstrap_does_not_treat_redis_failure_as_anonymous(self):
        self.sessions.get.side_effect = ConnectionError("Redis unavailable")
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["success"])
        self.assertTrue(response.json()["error"]["retryable"])

    def test_failed_login_never_creates_session(self):
        self.service.login_user.side_effect = LoginFailedError("Login failed")
        response = self.client.post("/auth/login", json={"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], {"code": 500, "message": "Login failed", "retryable": False})
        self.sessions.create.assert_not_called()
        self.assertNotIn("set-cookie", response.headers)

    def test_validation_does_not_echo_password(self):
        response = self.client.post("/auth/register", json={"username": "Alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["success"])
        self.assertNotIn(PASSWORD, response.text)
        self.service.register_user.assert_not_called()

    def test_registration_envelope_does_not_create_session(self):
        self.service.register_user.return_value = self.account
        response = self.client.post("/auth/register", json=registration().model_dump())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.sessions.create.assert_not_called()
        self.assertNotIn("set-cookie", response.headers)

    def test_duplicate_registration_envelope(self):
        self.service.register_user.side_effect = UserExistsError("Username already exists")
        response = self.client.post("/auth/register", json=registration().model_dump())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["message"], "Username already exists")

    def test_another_users_uuid_is_rejected(self):
        self.sessions.get.return_value = self.account
        response = self.client.get(f"/auth/username/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 500)
        self.service.get_username_by_id.assert_not_called()

    def test_current_user_can_read_username(self):
        self.sessions.get.return_value = self.account
        self.service.get_username_by_id.return_value = self.account.username
        response = self.client.get(f"/auth/username/{self.account.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"username": "Alice"})

    def test_missing_session_is_rejected(self):
        self.sessions.get.side_effect = SessionRequiredError("Please log in again")
        response = self.client.get(f"/auth/username/{self.account.id}")
        self.assertEqual(response.status_code, 500)
        self.service.get_username_by_id.assert_not_called()

    def test_logout_clears_cookie(self):
        self.client.cookies.set(settings.session_cookie_name, "old-session")
        response = self.client.post("/auth/logout")
        self.assertTrue(response.json()["success"])
        self.sessions.delete.assert_called_once_with("old-session")
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_unexpected_errors_are_sanitized(self):
        self.service.register_user.side_effect = RuntimeError(PASSWORD)
        response = self.client.post("/auth/register", json=registration().model_dump())
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(PASSWORD, response.text)
        self.assertTrue(response.json()["error"]["retryable"])


class SessionTests(unittest.TestCase):
    def test_missing_or_expired_session_is_rejected(self):
        redis = Mock()
        store = SessionStore(redis)
        with self.assertRaises(SessionRequiredError):
            store.get(None)
        redis.eval.assert_not_called()
        redis.eval.return_value = []
        with self.assertRaises(SessionRequiredError):
            store.get("expired")

    def test_create_and_refresh_use_separate_credentials(self):
        redis = Mock()
        store = SessionStore(redis)
        user = UserResponse(id=uuid.uuid4(), username="Alice")
        token = store.create(user)
        self.assertNotEqual(token, str(user.id))
        self.assertGreaterEqual(len(token), 40)
        redis.eval.return_value = [str(user.id), user.username]
        self.assertEqual(store.get(token), user)


class StartupTests(unittest.TestCase):
    def test_application_lifespan_and_health_without_network(self):
        from backend.main import app

        # Constructing the client is lazy; this smoke test never sends Redis commands.
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertTrue(hasattr(app.state, "redis"))


if __name__ == "__main__":
    unittest.main()
