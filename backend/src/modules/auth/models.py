import uuid
from sqlalchemy import UUID, CheckConstraint, String, UniqueConstraint, text

from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = 'users'
    # Match the deployed account table; changing this name would hide existing accounts.
    __table_args__ = (
        UniqueConstraint("username", name="users_username_key"),
        CheckConstraint("char_length(username) BETWEEN 1 AND 20 AND username !~ '[^A-Za-z0-9]'", name="user_username_format"),
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="user_password_hash_format"),
        {"schema": "public"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(String(20, collation="C"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    def __str__(self):
        return f"User(id={self.id}, username={self.username})"
