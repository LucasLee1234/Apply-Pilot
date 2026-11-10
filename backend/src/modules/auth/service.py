import uuid

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from modules.auth.exceptions import LoginFailedError, UserNotFoundError, UserExistsError
from modules.auth.repository import UserRepository
from modules.auth.schemas import LoginRequest, UserRegister, UserResponse
from modules.auth.security import DUMMY_PASSWORD_HASH, hash_password, verify_password


class UserService:

    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)

    def get_username_by_id(self, user_id: uuid.UUID) -> str:
        user_id = uuid.UUID(str(user_id))
        user = self.user_repository.get_user_by_id(user_id)

        if user is None:
            raise UserNotFoundError("User not found")

        return user.username

    def register_user(self, user: UserRegister) -> UserResponse:
        user = UserRegister.model_validate(user.model_dump() if isinstance(user, UserRegister) else user)
        existing_user = self.user_repository.get_user_by_username(user.username)
        if existing_user is not None:
            raise UserExistsError("Username already exists")
        password_hash = hash_password(user.password)
        try:
            new_user = self.user_repository.create_user_by_username_password(
                username=user.username,
                password_hash=password_hash
            )

            self.db.commit()

        except IntegrityError as exc:
            self.db.rollback()
            # The precheck can race; only the username constraint means a duplicate account.
            diagnostic = getattr(exc.orig, "diag", None)
            if getattr(diagnostic, "constraint_name", None) in {"users_username_key", "user_username_unique"}:
                raise UserExistsError("Username already exists") from exc
            raise
        except Exception:
            self.db.rollback()
            raise

        return UserResponse(username=new_user.username, id=new_user.id)

    def login_user(self, username: str, password: str) -> UserResponse:
        request = LoginRequest.model_validate({"username": username, "password": password})
        username, password = request.username, request.password
        user = self.user_repository.get_user_by_username(username)
        # Use the same message for unknown users and incorrect passwords.
        valid_password = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if user is None or not valid_password:
            raise LoginFailedError("Login failed")
        return UserResponse.model_validate(user)
