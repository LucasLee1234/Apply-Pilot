"""Optional PostgreSQL concurrency tests in an isolated, disposable schema.

Set PROFILE_CONFIRMATION_POSTGRES_TEST_URL to a disposable PostgreSQL database.
Only a generated schema is created and dropped; public application tables are unused.
Redis is mocked here; its actual Lua is covered by PROFILE_DRAFT_REDIS_TEST_URL.
"""

import json
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

import test_profile_preview as fixtures
from modules.auth.models import Base, Users
from modules.profile.confirmations import ConfirmationService, ProfileConfirmationStore
from modules.profile.drafts import ProfileDraftStore, ProfileDraftService
from modules.profile.exceptions import ProfileVersionConflictError, ConfirmationValidationError
from modules.profile.models import ApplicantProfile, ApplicantSkill, ProfileConfirmationReceipt
from modules.profile.preview import ProfilePreviewService
from modules.profile.preview_schemas import PreviewProfileRequest
from modules.profile.service import ApplicantProfileService
from modules.profile.schemas import SaveProfileDraftRequest
from redis import Redis


@unittest.skipUnless(os.environ.get('PROFILE_CONFIRMATION_POSTGRES_TEST_URL'), 'Optional PostgreSQL concurrency integration')
class ConfirmationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            os.environ['PROFILE_CONFIRMATION_POSTGRES_TEST_URL'],
            connect_args={'connect_timeout': 3, 'options': '-c statement_timeout=10000 -c lock_timeout=5000'},
        )
        self.addCleanup(self.engine.dispose)
        self.schema = 'confirmation_test_' + uuid.uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(CreateSchema(self.schema))
        self.addCleanup(self.drop_schema)
        self.bound = self.engine.execution_options(schema_translate_map={'public': self.schema})
        Base.metadata.create_all(self.bound)
        self.user_id, self.version = uuid.uuid4(), uuid.uuid4()
        with Session(self.bound) as db:
            db.add(Users(id=self.user_id, username='ConcurrencyTest', password_hash='$argon2id$synthetic'))
            db.commit()
        self.drafts, self.store = Mock(spec=ProfileDraftStore), Mock(spec=ProfileConfirmationStore)
        self.drafts.delete_old_draft.return_value = 1

    def drop_schema(self):
        with self.engine.begin() as connection:
            connection.execute(DropSchema(self.schema, cascade=True))

    def prepare(self, data, base_version):
        now = datetime.now(timezone.utc)
        self.drafts.get.return_value = {
            'user_id': str(self.user_id), 'version': str(self.version),
            'created_at': str(int(now.timestamp())), 'updated_at': str(int(now.timestamp())),
            'expires_at': str(int(now.timestamp()) + 604800), 'data': json.dumps(data, default=str),
        }
        self.store.create.return_value = ('token', now + timedelta(minutes=15))
        with Session(self.bound) as db:
            ProfilePreviewService(db, self.drafts, self.store).preview(self.user_id, PreviewProfileRequest(
                draft_version=self.version, expected_profile_version=base_version,
            ))
        self.store.get.return_value = {
            'user_id': str(self.user_id), 'draft_version': str(self.version),
            'created_at': str(int(now.timestamp())), 'expires_at': str(int(now.timestamp()) + 900),
            'status': 'awaiting_confirmation', 'payload': self.store.create.call_args.args[2],
        }

    def concurrently_confirm(self, tokens):
        barrier = threading.Barrier(2)

        def attempt(token):
            with Session(self.bound) as db:
                barrier.wait(timeout=5)
                try:
                    return ConfirmationService(self.store, self.drafts, db).confirm(token, self.user_id)
                except ProfileVersionConflictError:
                    return 'conflict'

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt, token) for token in tokens]
            return [future.result(timeout=15) for future in futures]

    def test_same_confirmation_creates_profile_only_once(self):
        self.prepare({'profile': fixtures.valid_profile()}, None)
        results = self.concurrently_confirm(['token', 'token'])
        self.assertEqual(results[0], results[1])
        self.store.claim.assert_called_once()
        with Session(self.bound) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ApplicantProfile)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProfileConfirmationReceipt)), 1)

    def test_two_approvals_for_same_baseline_have_one_winner(self):
        with Session(self.bound) as db:
            ApplicantProfileService(db).add_applicant_profile(fixtures.valid_profile(), self.user_id)
            db.commit()
        self.prepare({'skills': [{'name': 'Rust'}]}, 1)
        results = self.concurrently_confirm(['token-one', 'token-two'])
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count('conflict'), 1)
        with Session(self.bound) as db:
            self.assertEqual(db.scalar(select(ApplicantProfile.version)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(ApplicantSkill)), 1)


@unittest.skipUnless(
    os.environ.get('PROFILE_CONFIRMATION_POSTGRES_TEST_URL') and os.environ.get('PROFILE_DRAFT_REDIS_TEST_URL'),
    'Optional combined PostgreSQL and Redis integration',
)
class ConfirmationLiveServicesTests(unittest.TestCase):
    """Exercise real SQL commits and real Lua using only isolated test records."""

    def setUp(self):
        self.sql = ConfirmationConcurrencyTests('test_same_confirmation_creates_profile_only_once')
        self.addCleanup(self.sql.doCleanups)
        self.sql.setUp()
        self.redis = Redis.from_url(os.environ['PROFILE_DRAFT_REDIS_TEST_URL'], decode_responses=True,
                                    socket_connect_timeout=3, socket_timeout=3)
        self.addCleanup(self.redis.close)
        self.user_id = self.sql.user_id
        self.drafts = ProfileDraftStore(self.redis)
        self.store = ProfileConfirmationStore(self.redis)
        self.addCleanup(self.redis.delete, self.drafts.prefix + str(self.user_id))

    def prepare(self, data, base_version):
        current = ProfileDraftService(self.drafts).get_draft(self.user_id)
        draft = ProfileDraftService(self.drafts).save_draft(self.user_id, SaveProfileDraftRequest(
            expected_version=current.version if current else None, data=json.loads(json.dumps(data, default=str)),
        ))
        with Session(self.sql.bound) as db:
            proposal = ProfilePreviewService(db, self.drafts, self.store).preview(self.user_id, PreviewProfileRequest(
                draft_version=draft.version, expected_profile_version=base_version,
            ))
        self.addCleanup(self.redis.delete, self.store.prefix + str(self.user_id) + ':' + proposal.confirmation_id)
        return proposal

    def confirm(self, token):
        with Session(self.sql.bound) as db:
            return ConfirmationService(self.store, self.drafts, db).confirm(token, self.user_id)

    def test_create_edit_delete_and_receipt_replay_after_redis_expiration(self):
        proposal = self.prepare({'profile': fixtures.valid_profile(), 'skills': [{'name': 'Python'}]}, None)
        first = self.confirm(proposal.confirmation_id)
        self.assertEqual(first['status'], 'completed')
        self.assertEqual(first['cleanup']['draft'], 'deleted')
        self.assertIsNone(ProfileDraftService(self.drafts).get_draft(self.user_id))
        skill_id = first['saved']['skills'][0]['id']
        edit = self.prepare({'skills': [{'id': skill_id, 'name': 'Rust'}, {'name': 'SQL'}]}, 1)
        second = self.confirm(edit.confirmation_id)
        self.assertEqual(second['profile_version'], 2)
        self.assertEqual({row['name'] for row in second['saved']['skills']}, {'Rust', 'SQL'})
        removal = self.prepare({'skills': [{'id': skill_id}]}, 2)
        third = self.confirm(removal.confirmation_id)
        self.assertEqual(third['profile_version'], 3)
        self.assertEqual([row['name'] for row in third['saved']['skills']], ['SQL'])
        self.redis.delete(self.store.prefix + str(self.user_id) + ':' + proposal.confirmation_id)
        replay = self.confirm(proposal.confirmation_id)
        self.assertEqual(replay['saved'], first['saved'])
        self.assertEqual(replay['profile_version'], 1)
        with Session(self.sql.bound) as db:
            self.assertEqual(db.scalar(select(ApplicantProfile.version)), 3)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProfileConfirmationReceipt)), 3)

    def test_sql_failure_retains_draft_and_processing_proposal_can_retry(self):
        proposal = self.prepare({'profile': fixtures.valid_profile(), 'skills': [{'name': 'Python'}]}, None)
        with Session(self.sql.bound) as db:
            service = ConfirmationService(self.store, self.drafts, db)
            with patch.object(service.profile_service.applicant_skill_repository, 'insert_skill',
                              side_effect=RuntimeError('Synthetic insertion failure')):
                with self.assertRaisesRegex(RuntimeError, 'Synthetic insertion failure'):
                    service.confirm(proposal.confirmation_id, self.user_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(ApplicantProfile)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProfileConfirmationReceipt)), 0)
        self.assertIsNotNone(ProfileDraftService(self.drafts).get_draft(self.user_id))
        self.assertEqual(self.store.get(self.user_id, proposal.confirmation_id)['status'], 'processing')
        result = self.confirm(proposal.confirmation_id)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['profile_version'], 1)

    def test_cancel_preserves_draft_and_blocks_confirm_with_real_stores(self):
        proposal = self.prepare({'profile': fixtures.valid_profile()}, None)
        with Session(self.sql.bound) as db:
            service = ConfirmationService(self.store, self.drafts, db)
            result = service.cancel(proposal.confirmation_id, self.user_id)
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual(self.store.get(self.user_id, proposal.confirmation_id)['status'], 'cancelled')
            with self.assertRaises(ConfirmationValidationError):
                service.confirm(proposal.confirmation_id, self.user_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(ApplicantProfile)), 0)
        self.assertIsNotNone(ProfileDraftService(self.drafts).get_draft(self.user_id))
