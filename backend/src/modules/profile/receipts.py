"""SQL serialization and durable replay of confirmation outcomes."""

import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modules.profile.models import ApplicantProfile, ProfileConfirmationReceipt


class ConfirmationReceiptRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock(self, user_id: uuid.UUID):
        # Serialize even first-profile creation, where no profile row exists yet.
        # Locks are transaction-scoped and released on commit, rollback, or disconnect.
        if self.db.get_bind().dialect.name == "postgresql":
            key = int.from_bytes(hashlib.sha256(user_id.bytes).digest()[:8], "big", signed=True)
            self.db.execute(select(func.pg_advisory_xact_lock(key)))
        self.db.execute(select(ApplicantProfile.id).where(
            ApplicantProfile.user_id == user_id,
        ).with_for_update())

    @staticmethod
    def token_hash(confirmation_id: str) -> str:
        return hashlib.sha256(confirmation_id.encode()).hexdigest()

    def get(self, user_id: uuid.UUID, confirmation_id: str) -> dict | None:
        return self.db.execute(select(ProfileConfirmationReceipt.result).where(
            ProfileConfirmationReceipt.user_id == user_id,
            ProfileConfirmationReceipt.confirmation_hash == self.token_hash(confirmation_id),
        )).scalar_one_or_none()

    def add(self, user_id: uuid.UUID, confirmation_id: str, result: dict):
        self.db.add(ProfileConfirmationReceipt(
            user_id=user_id, confirmation_hash=self.token_hash(confirmation_id), result=result,
        ))
