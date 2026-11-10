import uuid

from sqlalchemy import select, insert
from sqlalchemy.orm import Session

from modules.auth.models import Users


class UserRepository:
    def __init__(self, db: Session):
        self.db = db
    def get_user_by_id(self, user_id: uuid.UUID) -> Users | None:
        stmt = select(Users).where(Users.id == user_id)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_user_by_username(self, username: str) -> Users | None:
        stmt = select(Users).where(Users.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_user_by_username_password(
        self,
        username: str,
        password_hash: str,
    ) -> Users:
        stmt = insert(Users).values(username=username, password_hash=password_hash).returning(Users)

        return self.db.execute(stmt).scalar_one()
