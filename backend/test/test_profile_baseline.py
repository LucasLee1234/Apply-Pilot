import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from sqlalchemy import delete, event, insert, select, update
from sqlalchemy.orm import Session

import test_profile as fixtures
from modules.profile.confirmations import ConfirmationService, ProfileConfirmationStore
from modules.profile.drafts import ProfileDraftStore
from modules.profile.exceptions import ProfileVersionConflictError
from modules.profile.models import ApplicantProfile, ApplicantSkill, WorkExperience
from modules.profile.preview import ProfilePreviewService
from modules.profile.preview_schemas import PreviewProfileRequest
from modules.profile.utils import SECTIONS, get_fingerprint, read_baseline


class BaselineValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProfileTests("test_complete_profile_filters_every_table_by_owner")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.engine = self.fixture.engine
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.user_id = self.fixture.user_id
        self.version = uuid.uuid4()
        now = int(datetime.now(timezone.utc).timestamp())
        self.drafts = Mock(spec=ProfileDraftStore)
        self.drafts.get.return_value = {
            "user_id": str(self.user_id), "version": str(self.version), "created_at": str(now),
            "updated_at": str(now), "expires_at": str(now + 604800),
            "data": json.dumps({"profile": {"first_name": "Reviewed"}}),
        }
        self.confirmations = Mock(spec=ProfileConfirmationStore)
        self.confirmations.create.return_value = ("test-proposal", datetime.now(timezone.utc) + timedelta(minutes=15))
        self.preview = ProfilePreviewService(self.db, self.drafts, self.confirmations)
        self.service = ConfirmationService(self.confirmations, self.drafts, self.db)

    def prepare(self, user_id=None, expected_version=1, data=None):
        if user_id is not None:
            self.user_id = user_id
            self.drafts.get.return_value["user_id"] = str(user_id)
        if data is not None:
            self.drafts.get.return_value["data"] = json.dumps(data, default=str)
        result = self.preview.preview(self.user_id, PreviewProfileRequest(
            draft_version=self.version, expected_profile_version=expected_version,
        ))
        payload = self.confirmations.create.call_args.args[2]
        now = int(datetime.now(timezone.utc).timestamp())
        self.confirmations.get.return_value = {
            "user_id": str(self.user_id), "draft_version": str(self.version),
            "created_at": str(now), "expires_at": str(now + 900),
            "status": "awaiting_confirmation", "payload": payload,
        }
        return result

    def test_same_baseline_from_preview_passes_confirmation(self):
        self.prepare()
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.split()[0].upper())
        event.listen(self.engine, "before_cursor_execute", capture)
        record = self.service.validate_confirmation(self.user_id, "test-proposal")
        self.assertEqual(record.payload.proposed.profile.first_name, "Reviewed")
        self.assertEqual(set(statements), {"SELECT"})
        self.assertEqual(self.db.scalar(select(ApplicantProfile.first_name).where(ApplicantProfile.user_id == self.user_id)), "Reader")

    def test_first_profile_allows_none_version_and_shared_null_fingerprint(self):
        new_user_id = uuid.uuid4()
        fields = fixtures.profile(new_user_id, "New")
        from modules.profile.validation import FormalProfileInput
        data = {"profile": {name: fields[name] for name in FormalProfileInput.model_fields}}
        self.prepare(new_user_id, None, data)
        record = self.service.validate_confirmation(new_user_id, "test-proposal")
        self.assertIsNone(record.payload.base_profile_version)
        self.assertEqual(record.payload.base_snapshot_hash, get_fingerprint(
            None, None, {"profile": {}, **{section: [] for section in SECTIONS}},
        ))

    def test_creation_conflicts_if_a_formal_profile_appeared(self):
        new_user_id = uuid.uuid4()
        fields = fixtures.profile(new_user_id, "New")
        from modules.profile.validation import FormalProfileInput
        self.prepare(new_user_id, None, {"profile": {name: fields[name] for name in FormalProfileInput.model_fields}})
        self.db.execute(insert(ApplicantProfile), fields)
        with self.assertRaises(ProfileVersionConflictError):
            self.service.validate_confirmation(new_user_id, "test-proposal")

    def test_update_conflicts_if_formal_profile_disappeared(self):
        self.prepare()
        self.db.execute(delete(ApplicantProfile).where(ApplicantProfile.user_id == self.user_id))
        with self.assertRaises(ProfileVersionConflictError):
            self.service.validate_confirmation(self.user_id, "test-proposal")

    def test_updated_version_is_detected_even_with_a_cached_orm_instance(self):
        cached = self.db.scalar(select(ApplicantProfile).where(ApplicantProfile.user_id == self.user_id))
        self.prepare()
        self.db.execute(update(ApplicantProfile).where(ApplicantProfile.user_id == self.user_id).values(version=2),
                        execution_options={"synchronize_session": False})
        self.assertEqual(cached.version, 1)
        with self.assertRaises(ProfileVersionConflictError):
            self.service.validate_confirmation(self.user_id, "test-proposal")
        self.assertEqual(cached.version, 2)

    def test_changed_profile_text_without_version_increment_is_detected(self):
        self.prepare()
        self.db.execute(update(ApplicantProfile).where(ApplicantProfile.user_id == self.user_id).values(city="Changed City"))
        with self.assertRaises(ProfileVersionConflictError):
            self.service.validate_confirmation(self.user_id, "test-proposal")

    def test_child_changes_without_version_increment_are_detected(self):
        for operation in ("update", "insert", "delete", "reorder"):
            with self.subTest(operation=operation):
                self.prepare()
                savepoint = self.db.begin_nested()
                try:
                    if operation == "update":
                        self.db.execute(update(WorkExperience).where(WorkExperience.user_id == self.user_id).values(company="Changed Company"))
                    elif operation == "insert":
                        self.db.execute(insert(ApplicantSkill), fixtures.owned(self.user_id, name="Rust", sort_order=3))
                    elif operation == "delete":
                        self.db.execute(delete(ApplicantSkill).where(ApplicantSkill.user_id == self.user_id))
                    else:
                        self.db.execute(update(ApplicantSkill).where(ApplicantSkill.user_id == self.user_id).values(sort_order=7))
                    with self.assertRaises(ProfileVersionConflictError):
                        self.service.validate_confirmation(self.user_id, "test-proposal")
                finally:
                    savepoint.rollback()

    def test_changed_profile_identity_with_same_version_is_detected(self):
        self.prepare()
        self.db.execute(update(ApplicantProfile).where(ApplicantProfile.user_id == self.user_id).values(id=uuid.uuid4()))
        with self.assertRaises(ProfileVersionConflictError):
            self.service.validate_confirmation(self.user_id, "test-proposal")

    def test_other_users_changes_do_not_invalidate_this_proposal(self):
        self.prepare()
        self.db.execute(update(ApplicantSkill).where(ApplicantSkill.user_id == self.fixture.other_id).values(name="Other Skill"))
        self.service.validate_confirmation(self.user_id, "test-proposal")

    def test_shared_fingerprint_retains_previous_canonical_format(self):
        import hashlib
        current, baseline = read_baseline(self.service.db, self.user_id)
        old_binding = {"profile_id": str(current.id), "profile_version": current.version, "data": baseline}
        old_hash = hashlib.sha256(json.dumps(old_binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(get_fingerprint(str(current.id), current.version, baseline), old_hash)


if __name__ == "__main__":
    unittest.main()
