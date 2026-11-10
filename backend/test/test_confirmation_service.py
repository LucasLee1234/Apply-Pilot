r"""Confirmation storage, validation, grouping, execution, and SQL-flow tests.

Run from backend/ in PowerShell:
    $env:PYTHONPATH = 'src'
    $env:DATABASE_URL = 'sqlite://'
    $env:REDIS_URL = 'redis://localhost:6379/0'
    $env:APP_TIMEZONE = 'timezone.utc'
    .\.venv\Scripts\python.exe -B -m unittest discover -s test -p test_confirmation_service.py -v

Normal runs use mocked Redis and in-memory SQLite, never application data.
To opt into the live Redis tests, set PROFILE_DRAFT_REDIS_TEST_URL to a
disposable Redis database. They create isolated UUID-prefixed records and clean
up only their own keys; they never call FLUSHDB or FLUSHALL.
"""

import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Column, MetaData, Table, create_engine, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import test_profile_preview as preview_fixtures
from common.database import get_db
from common.exception_handlers import register_exception_handlers
from modules.auth.dependencies import get_current_user
from modules.auth.schemas import UserResponse
from common.config import settings
from modules.profile.confirmations import (
    CREATE_CONFIRMATION, ConfirmationService, ProfileConfirmationStore, get_profile_confirmation_store,
)
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore, get_profile_draft_store
from modules.profile.confirmations import get_profile_confirmation_store
from modules.profile.route import router
from modules.profile.exceptions import (
    ConfirmationNotFoundError, ConfirmationOwnershipError, ConfirmationStorageError,
    ConfirmationValidationError, DraftConflictError, DraftNotFoundError, ProfileVersionConflictError,
    DraftStorageError,
)
from modules.profile.models import ApplicantProfile, ApplicantSkill, EducationEntry, SocialLink, WorkExperience, ProfileConfirmationReceipt
from modules.profile.preview import ProfilePreviewService
from modules.profile.preview_schemas import PreviewProfileRequest, ProfileChange, ProfileConfirmationRecord
from modules.profile.schemas import SaveProfileDraftRequest
from modules.profile.service import ApplicantProfileService
from modules.profile.utils import SECTIONS, get_fingerprint
from modules.profile.validation import FormalProfileSnapshot, FormalProfileInput


def payload(user_id, version):
    proposed = FormalProfileSnapshot(profile=preview_fixtures.valid_profile(user_id))
    return {
        "user_id": str(user_id), "draft_version": str(version), "base_profile_version": None,
        "base_snapshot_hash": get_fingerprint(None, None, {"profile": {}, **{section: [] for section in SECTIONS}}),
        "proposed": proposed.model_dump(mode="json"), "changes": [],
    }


def empty_database():
    db = Mock(spec=Session)
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []
    return db


class ConfirmationStoreTests(unittest.TestCase):
    """Redis transport is mocked; these tests never contact the configured server."""

    def setUp(self):
        self.redis = Mock(spec=Redis)
        self.store = ProfileConfirmationStore(self.redis)
        self.user_id, self.version = uuid.uuid4(), uuid.uuid4()

    def test_create_binds_owner_draft_payload_and_expiration(self):
        expires = 1794000000
        body = '{"proposed":{"skills":[]}}'
        self.redis.eval.return_value = [1, expires]
        with patch('modules.profile.confirmations.secrets.token_urlsafe', return_value='opaque-token') as token:
            result, expiry = self.store.create(self.user_id, self.version, body)
        token.assert_called_once_with(32)
        self.assertEqual(result, 'opaque-token')
        self.assertEqual(expiry, datetime.fromtimestamp(expires, timezone.utc))
        self.redis.eval.assert_called_once_with(
            CREATE_CONFIRMATION, 2, ProfileDraftStore.prefix + str(self.user_id),
            self.store.prefix + str(self.user_id) + ':opaque-token',
            str(self.version), str(self.user_id), body, settings.profile_confirmation_ttl_seconds,
        )

    def test_stale_or_expired_draft_cannot_create_confirmation(self):
        self.redis.eval.return_value = [0]
        with self.assertRaises(DraftConflictError):
            self.store.create(self.user_id, self.version, '{}')

    def test_token_collision_is_a_storage_error(self):
        self.redis.eval.return_value = [-1]
        with self.assertRaises(ConfirmationStorageError):
            self.store.create(self.user_id, self.version, '{}')

    def test_create_outage_is_retryable_and_does_not_expose_connection_details(self):
        self.redis.eval.side_effect = RedisConnectionError('private redis password')
        with self.assertRaises(ConfirmationStorageError) as caught:
            self.store.create(self.user_id, self.version, '{}')
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn('private', str(caught.exception))

    def test_get_scopes_key_by_owner_and_maps_empty_hash_to_none(self):
        stored = {'status': 'awaiting_confirmation'}
        self.redis.hgetall.return_value = stored
        self.assertIs(self.store.get(self.user_id, 'token'), stored)
        self.redis.hgetall.assert_called_once_with(self.store.prefix + str(self.user_id) + ':token')
        self.redis.hgetall.return_value = {}
        self.assertIsNone(self.store.get(self.user_id, 'token'))

    def test_different_owners_use_different_keys_for_the_same_token(self):
        self.redis.hgetall.return_value = {}
        owners = [self.user_id, uuid.uuid4()]
        for owner in owners:
            self.store.get(owner, 'same-token')
        self.assertNotEqual(*[call.args[0] for call in self.redis.hgetall.call_args_list])

    def test_dependency_uses_the_application_redis_client(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=self.redis)))
        self.assertIs(get_profile_confirmation_store(request).redis, self.redis)


class ConfirmationServiceTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.version = uuid.uuid4()
        self.now = int(datetime.now(timezone.utc).timestamp())
        self.store = Mock(spec=ProfileConfirmationStore)
        self.drafts = Mock(spec=ProfileDraftStore)
        self.raw = {
            "user_id": str(self.user_id), "draft_version": str(self.version),
            "created_at": str(self.now), "expires_at": str(self.now + 900),
            "status": "awaiting_confirmation", "payload": json.dumps(payload(self.user_id, self.version)),
        }
        self.store.get.return_value = self.raw
        self.drafts.get.return_value = {
            "user_id": str(self.user_id), "version": str(self.version),
            "created_at": str(self.now), "updated_at": str(self.now),
            "expires_at": str(self.now + 604800), "data": "{}",
        }
        self.service = ConfirmationService(self.store, self.drafts, empty_database())

    def test_valid_redis_record_is_parsed_and_returned(self):
        record = self.service.validate_confirmation(self.user_id, "opaque-token-not-a-uuid")
        self.assertIsInstance(record, ProfileConfirmationRecord)
        self.assertEqual(record.draft_version, self.version)
        self.assertEqual(record.payload.draft_version, self.version)
        self.assertEqual(record.expires_at.tzinfo, timezone.utc)
        self.assertEqual(record.payload.proposed.profile.first_name, "Example")
        self.store.get.assert_called_once_with(self.user_id, "opaque-token-not-a-uuid")
        self.store.create.assert_not_called()
        self.drafts.save.assert_not_called()

    def test_success_returns_the_existing_parsed_record(self):
        record = self.service.get_confirmation(self.user_id, "token")
        self.service.get_confirmation = Mock(return_value=record)
        self.assertIs(self.service.validate_confirmation(self.user_id, "token"), record)

    def test_missing_confirmation_is_not_a_storage_outage(self):
        self.store.get.return_value = None
        self.assertIsNone(self.service.get_confirmation(self.user_id, "missing"))
        with self.assertRaises(ConfirmationNotFoundError) as caught:
            self.service.validate_confirmation(self.user_id, "missing")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertFalse(getattr(caught.exception, "retryable", False))
        self.drafts.get.assert_not_called()

    def test_saved_status_is_preserved_and_nonpending_states_are_rejected(self):
        for status in ("processing", "completed", "cancelled"):
            with self.subTest(status=status):
                self.raw["status"] = status
                self.assertEqual(self.service.get_confirmation(self.user_id, "token").status, status)
                with self.assertRaises(ConfirmationValidationError) as caught:
                    self.service.validate_confirmation(self.user_id, "token")
                self.assertEqual(caught.exception.status_code, 409)
        self.drafts.get.assert_not_called()

    def test_expired_confirmation_is_rejected(self):
        self.raw["expires_at"] = str(self.now - 1)
        with self.assertRaises(ConfirmationValidationError):
            self.service.validate_confirmation(self.user_id, "expired")
        self.drafts.get.assert_not_called()

    def test_both_outer_and_payload_owner_must_match(self):
        for field in ("outer", "payload"):
            with self.subTest(field=field):
                self.raw["user_id"] = str(self.user_id)
                content = payload(self.user_id, self.version)
                if field == "outer":
                    self.raw["user_id"] = str(uuid.uuid4())
                else:
                    content["user_id"] = str(uuid.uuid4())
                self.raw["payload"] = json.dumps(content)
                with self.assertRaises(ConfirmationOwnershipError) as caught:
                    self.service.validate_confirmation(self.user_id, "foreign")
                self.assertEqual(caught.exception.status_code, 403)
        self.drafts.get.assert_not_called()

    def test_missing_or_expired_draft_is_a_business_error(self):
        draft = self.drafts.get.return_value
        for value in (None, {**draft, "expires_at": str(self.now - 1)}):
            with self.subTest(value=value):
                self.drafts.get.return_value = value
                with self.assertRaises(DraftNotFoundError) as caught:
                    self.service.validate_confirmation(self.user_id, "token")
                self.assertEqual(caught.exception.status_code, 404)

    def test_all_draft_versions_must_match(self):
        content = payload(self.user_id, uuid.uuid4())
        self.raw["payload"] = json.dumps(content)
        with self.assertRaises(DraftConflictError):
            self.service.validate_confirmation(self.user_id, "token")
        self.raw["payload"] = json.dumps(payload(self.user_id, self.version))
        self.drafts.get.return_value["version"] = str(uuid.uuid4())
        with self.assertRaises(DraftConflictError):
            self.service.validate_confirmation(self.user_id, "token")

    def test_malformed_storage_stays_a_storage_error(self):
        valid = dict(self.raw)
        cases = [
            {**valid, "payload": "not json"}, {**valid, "created_at": "invalid"},
            {**valid, "status": "unknown-state"}, {key: value for key, value in valid.items() if key != "draft_version"},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.store.get.return_value = value
                with self.assertRaises(ConfirmationStorageError):
                    self.service.get_confirmation(self.user_id, "token")

    def test_redis_outage_remains_retryable_storage_error(self):
        redis = Mock()
        redis.hgetall.side_effect = RedisConnectionError("private connection information")
        store = ProfileConfirmationStore(redis)
        with self.assertRaises(ConfirmationStorageError) as caught:
            store.get(self.user_id, "token")
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("private", str(caught.exception))

    def test_invalid_uuid_timestamp_and_payload_shape_are_storage_errors(self):
        valid = dict(self.raw)
        cases = [
            {**valid, 'user_id': 'invalid'}, {**valid, 'draft_version': 'invalid'},
            {**valid, 'expires_at': 'invalid'}, {**valid, 'expires_at': '1' * 100},
            {**valid, 'payload': '[]'}, {**valid, 'payload': '{}'},
            {**valid, 'payload': json.dumps({**payload(self.user_id, self.version), 'base_snapshot_hash': 'bad'})},
        ]
        for stored in cases:
            with self.subTest(stored=stored), self.assertRaises(ConfirmationStorageError):
                self.service._response(self.user_id, stored)

    def test_confirmation_expiring_exactly_now_is_rejected(self):
        record = self.service.get_confirmation(self.user_id, 'token')
        self.service.get_confirmation = Mock(return_value=record)
        with patch('modules.profile.confirmations.datetime') as clock:
            clock.now.return_value = record.expires_at
            with self.assertRaises(ConfirmationValidationError):
                self.service.validate_confirmation(self.user_id, 'token')
        self.drafts.get.assert_not_called()

    def test_draft_expiring_exactly_now_is_rejected(self):
        now = datetime.fromtimestamp(self.now, timezone.utc)
        record = self.service.get_confirmation(self.user_id, 'token')
        self.service.get_confirmation = Mock(return_value=record)
        self.service.draft_service = Mock()
        self.service.draft_service.get_draft.return_value = SimpleNamespace(expires_at=now, version=self.version)
        with patch('modules.profile.confirmations.datetime') as clock:
            clock.now.return_value = now
            with self.assertRaises(DraftNotFoundError):
                self.service.validate_confirmation(self.user_id, 'token')

    def test_validation_rechecks_ownership_even_for_an_already_parsed_record(self):
        record = self.service.get_confirmation(self.user_id, 'token')
        record.user_id = uuid.uuid4()
        self.service.get_confirmation = Mock(return_value=record)
        with self.assertRaises(ConfirmationOwnershipError):
            self.service.validate_confirmation(self.user_id, 'token')
        self.drafts.get.assert_not_called()

    def test_formal_version_mismatches_include_creation_and_deletion(self):
        record = self.service.get_confirmation(self.user_id, 'token')
        for saved, reviewed in ((None, 1), (1, None), (2, 1)):
            with self.subTest(saved=saved, reviewed=reviewed):
                record.payload.base_profile_version = reviewed
                current = SimpleNamespace(id=uuid.uuid4(), version=saved) if saved else None
                with patch('modules.profile.confirmations.read_baseline', return_value=(current, {})):
                    with self.assertRaises(ProfileVersionConflictError):
                        self.service.validate_formal_profile(self.user_id, record)

    def test_matching_version_still_requires_matching_contents(self):
        record = self.service.get_confirmation(self.user_id, 'token')
        baseline = {'profile': {'first_name': 'Changed'}, **{section: [] for section in SECTIONS}}
        with patch('modules.profile.confirmations.read_baseline', return_value=(None, baseline)):
            with self.assertRaises(ProfileVersionConflictError):
                self.service.validate_formal_profile(self.user_id, record)

    def test_direct_formal_validation_rejects_foreign_owner_before_database_read(self):
        record = self.service.get_confirmation(self.user_id, 'token')
        for field in ('outer', 'payload'):
            with self.subTest(field=field):
                foreign = record.model_copy(deep=True)
                if field == 'outer':
                    foreign.user_id = uuid.uuid4()
                else:
                    foreign.payload.user_id = uuid.uuid4()
                with patch('modules.profile.confirmations.read_baseline') as read:
                    with self.assertRaises(ConfirmationOwnershipError):
                        self.service.validate_formal_profile(self.user_id, foreign)
                    read.assert_not_called()


class ConfirmationChangeTests(unittest.TestCase):
    """Exercise actual change grouping without database access."""

    def setUp(self):
        self.user_id = uuid.uuid4()
        self.service = ConfirmationService(Mock(), Mock(), empty_database())
        self.service.profile_service = Mock(spec=ApplicantProfileService)
        self.service.profile_service.applicant_profile_repository = Mock()

    def change(self, field, operation='update', after=None, before=None):
        return ProfileChange(field=field, operation=operation, before=before, after=after)

    def test_empty_changes_produce_an_empty_mapping(self):
        self.assertEqual(self.service._change([], self.user_id, None), {})
        self.service.profile_service.obtain_profile_by_user_id.assert_not_called()

    def test_new_profile_groups_fields_without_querying_for_a_missing_profile(self):
        changes = [self.change('profile.first_name', 'add', 'New'),
                   self.change('profile.last_name', 'add', 'Example')]
        self.assertEqual(self.service._change(changes, self.user_id, None), {
            'profile': {'id': '', 'data': {'first_name': 'New', 'last_name': 'Example'}},
        })
        self.service.profile_service.obtain_profile_by_user_id.assert_not_called()

    def test_existing_profile_queries_identity_once_and_preserves_explicit_null(self):
        profile_id = uuid.uuid4()
        self.service.profile_service.obtain_profile_by_user_id.return_value = SimpleNamespace(id=profile_id)
        changes = [self.change('profile.first_name', after='Changed'),
                   self.change('profile.preferred_name', after=None, before='Old')]
        self.assertEqual(self.service._change(changes, self.user_id, 1), {
            'profile': {'id': profile_id, 'data': {'first_name': 'Changed', 'preferred_name': None}},
        })
        self.service.profile_service.obtain_profile_by_user_id.assert_called_once_with(user_id=self.user_id)

    def test_updates_group_multiple_fields_and_multiple_ids_in_every_section(self):
        fields = {'skills': 'name', 'work_experiences': 'company',
                  'education_entries': 'school', 'social_links': 'url'}
        for section, field in fields.items():
            with self.subTest(section=section):
                first, second = str(uuid.uuid4()), str(uuid.uuid4())
                changes = [self.change(f'{section}[{first}].sort_order', after=2),
                           self.change(f'{section}[{first}].{field}', after='Changed'),
                           self.change(f'{section}[{second}].sort_order', after=3)]
                self.assertEqual(self.service._change(changes, self.user_id, 1), {
                    section: {first: {'sort_order': 2, field: 'Changed'}, second: {'sort_order': 3}},
                })

    def test_multiple_additions_and_removals_do_not_overwrite_in_any_section(self):
        for section in SECTIONS:
            with self.subTest(section=section):
                ids = [str(uuid.uuid4()) for _ in range(4)]
                changes = [self.change(f'{section}[{ids[0]}]', 'remove'),
                           self.change(f'{section}[{ids[1]}]', 'remove'),
                           self.change(f'{section}[{ids[2]}]', 'add', {'id': ids[2], 'sort_order': 1}),
                           self.change(f'{section}[{ids[3]}]', 'add', {'id': ids[3], 'sort_order': 2})]
                result = self.service._change(changes, self.user_id, 1)[section]
                self.assertEqual(len(result), 4)
                self.assertCountEqual([v for k, v in result.items() if k.startswith('remove:')], ids[:2])
                self.assertCountEqual([v['id'] for k, v in result.items() if k.startswith('add:')], ids[2:])

    def test_mixed_operations_stay_in_their_own_sections(self):
        first, second, third = [str(uuid.uuid4()) for _ in range(3)]
        changes = [self.change(f'skills[{first}]', 'add', {'id': first, 'name': 'Python'}),
                   self.change(f'social_links[{second}]', 'remove'),
                   self.change(f'work_experiences[{third}].company', after='Example')]
        result = self.service._change(changes, self.user_id, 1)
        self.assertEqual(list(result['skills'].values()), [{'id': first, 'name': 'Python'}])
        self.assertEqual(list(result['social_links'].values()), [second])
        self.assertEqual(result['work_experiences'], {third: {'company': 'Example'}})

    def test_unsupported_operation_is_rejected(self):
        # Bypass the Pydantic Literal to exercise the service's defensive branch.
        change = SimpleNamespace(field=f'skills[{uuid.uuid4()}]', operation='replace')
        with self.assertRaises(ConfirmationValidationError):
            self.service._change([change], self.user_id, 1)


class ConfirmationExecutionTests(unittest.TestCase):
    def setUp(self):
        self.user_id, self.version = uuid.uuid4(), uuid.uuid4()
        self.db = empty_database()
        self.service = ConfirmationService(Mock(), Mock(), self.db)
        self.service.profile_service = Mock(spec=ApplicantProfileService)
        self.service.profile_service.applicant_profile_repository = Mock()
        self.service.draft_store.delete_old_draft.return_value = 1
        saved = Mock()
        saved.profile.version = 1
        saved.model_dump.return_value = {"profile": {"version": 1}}
        self.service.profile_service.obtain_complete_profile_by_user_id.return_value = saved
        self.record = ProfileConfirmationRecord(
            user_id=self.user_id, draft_version=self.version, status='awaiting_confirmation',
            created_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            payload=payload(self.user_id, self.version),
        )
        self.service.validate_confirmation = Mock(return_value=self.record)

    def test_confirm_uses_validated_payload_and_saves_the_formatted_changes(self):
        skill_id = str(uuid.uuid4())
        self.record.payload.changes = [ProfileChange(
            field=f'skills[{skill_id}]', operation='add', before=None,
            after={'id': skill_id, 'name': 'Python', 'sort_order': 0},
        )]
        result = self.service.confirm('opaque-token', self.user_id)
        self.assertEqual(result['status'], 'completed')
        self.service.validate_confirmation.assert_called_once_with(user_id=self.user_id, confirmation_id='opaque-token', allow_processing=True)
        changes = self.service.profile_service.confirm_draft_save_applicant_information.call_args.args[0]
        self.assertEqual(list(changes['skills'].values()), [{'id': skill_id, 'name': 'Python', 'sort_order': 0}])
        self.service.profile_service.confirm_draft_save_applicant_information.assert_called_once_with(changes, self.user_id, commit=False)

    def test_confirm_passes_existing_profile_version_to_grouping(self):
        self.record.payload.base_profile_version = 7
        self.record.payload.changes = [ProfileChange(field='profile.first_name', operation='update', before='Old', after='New')]
        profile_id = uuid.uuid4()
        self.service.profile_service.obtain_profile_by_user_id.return_value = SimpleNamespace(id=profile_id)
        result = self.service.confirm('token', self.user_id)
        changes = self.service.profile_service.confirm_draft_save_applicant_information.call_args.args[0]
        self.assertEqual(changes['profile']['id'], profile_id)
        self.assertEqual(changes['profile']['data'], {'first_name': 'New'})

    def test_validation_failure_never_reaches_writer(self):
        for error in (ConfirmationNotFoundError, ConfirmationValidationError, ConfirmationOwnershipError,
                      DraftNotFoundError, DraftConflictError, ProfileVersionConflictError, ConfirmationStorageError):
            with self.subTest(error=error):
                self.service.validate_confirmation.side_effect = error('Rejected')
                with self.assertRaises(error):
                    self.service.confirm('token', self.user_id)
        self.service.profile_service.confirm_draft_save_applicant_information.assert_not_called()

    def test_grouping_failure_never_reaches_writer(self):
        with patch.object(self.service, '_change', side_effect=ConfirmationValidationError('Invalid change')):
            with self.assertRaises(ConfirmationValidationError):
                self.service.confirm('token', self.user_id)
        self.service.profile_service.confirm_draft_save_applicant_information.assert_not_called()

    def test_writer_failure_propagates_to_caller(self):
        self.service.profile_service.confirm_draft_save_applicant_information.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.service.confirm('token', self.user_id)
        self.db.commit.assert_not_called()


class ConfirmationSqlFlowTests(unittest.TestCase):
    """Real preview/service/repository code with SQLite and mocked Redis.

    PostgreSQL-specific CHECK constraints and foreign keys are deliberately not
    copied. Their behavior needs a separate disposable PostgreSQL integration run.
    Timestamp/version/UUID defaults are preserved to exercise actual inserts.
    """

    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, 'connect')
        def configure(connection, record):
            connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
            connection.execute("ATTACH DATABASE ':memory:' AS public")

        metadata = MetaData()
        for model in (ApplicantProfile, ApplicantSkill, WorkExperience, EducationEntry, SocialLink, ProfileConfirmationReceipt):
            columns = []
            for column in model.__table__.c:
                kind = column.type.copy()
                if hasattr(kind, 'collation'):
                    kind.collation = None
                columns.append(Column(column.name, kind, primary_key=column.primary_key,
                                      nullable=column.nullable, server_default=column.server_default))
            Table(model.__tablename__, metadata, *columns, schema='public')
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.user_id = uuid.uuid4()
        self.writer = ApplicantProfileService(self.db)
        self.drafts = Mock(spec=ProfileDraftStore)
        self.drafts.delete_old_draft.return_value = 1
        self.store = Mock(spec=ProfileConfirmationStore)
        self.preview = ProfilePreviewService(self.db, self.drafts, self.store)
        self.service = ConfirmationService(self.store, self.drafts, self.db)

    def section_data(self):
        return {
            'skills': {'name': 'Python'},
            'work_experiences': {'job_title': 'Engineer', 'company': 'Example Company',
                'start_year': 2022, 'start_month': 1, 'currently_employed': True,
                'role_description': 'Synthetic test experience'},
            'education_entries': {'school': 'Example University', 'degree': 'bachelor',
                'major': 'Computer Science', 'education_status': 'graduated',
                'graduation_year': 2021, 'graduation_month': 5, 'gpa': '3.750'},
            'social_links': {'platform': 'portfolio', 'url': 'https://example.com/test'},
        }

    def seed_profile(self, user_id=None):
        return self.writer.add_applicant_profile(preview_fixtures.valid_profile(), user_id or self.user_id)

    def seed_children(self, user_id=None):
        entries = {}
        for section, fields in self.section_data().items():
            entries[section] = self.writer.handler[section]['add'](
                {'id': str(uuid.uuid4()), **fields}, user_id=user_id or self.user_id,
            )
        return entries

    def prepare(self, data, base_version):
        version = uuid.uuid4()
        now = int(datetime.now(timezone.utc).timestamp())
        self.drafts.get.return_value = {
            'user_id': str(self.user_id), 'version': str(version),
            'created_at': str(now), 'updated_at': str(now), 'expires_at': str(now + 604800),
            'data': json.dumps(data, default=str),
        }
        self.store.create.return_value = ('test-confirmation', datetime.fromtimestamp(now + 900, timezone.utc))
        proposal = self.preview.preview(self.user_id, PreviewProfileRequest(
            draft_version=version, expected_profile_version=base_version,
        ))
        self.assertEqual(proposal.status, 'awaiting_confirmation')
        self.store.get.return_value = {
            'user_id': str(self.user_id), 'draft_version': str(version),
            'created_at': str(now), 'expires_at': str(now + 900), 'status': 'awaiting_confirmation',
            'payload': self.store.create.call_args.args[2],
        }
        return proposal

    def assert_saved_proposal(self, proposal):
        from modules.profile.utils import read_baseline
        _, baseline = read_baseline(self.db, self.user_id)
        self.assertEqual(baseline, proposal.proposed.model_dump(mode='json'))

    def test_create_profile_and_all_sections_preserves_preview_ids(self):
        proposal = self.prepare({
            'profile': FormalProfileInput.model_validate(preview_fixtures.valid_profile()).model_dump(mode='json'),
            **{section: [fields] for section, fields in self.section_data().items()},
        }, None)
        self.service.confirm('test-confirmation', self.user_id)
        self.assert_saved_proposal(proposal)
        profile = self.writer.obtain_profile_by_user_id(self.user_id)
        self.assertIsInstance(profile.id, uuid.UUID)
        self.assertEqual(profile.version, 1)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_partial_updates_across_all_sections_preserve_untouched_records(self):
        self.seed_profile()
        entries = self.seed_children()
        untouched_id = uuid.uuid4()
        self.writer.add_skill_profile({'id': str(untouched_id), 'name': 'SQL'}, self.user_id)
        self.db.commit()
        proposal = self.prepare({
            'profile': {'first_name': 'Changed'},
            'skills': [{'id': str(entries['skills'].id), 'name': 'Rust'}],
            'work_experiences': [{'id': str(entries['work_experiences'].id), 'company': 'Changed Company'}],
            'education_entries': [{'id': str(entries['education_entries'].id), 'gpa': None}],
            'social_links': [{'id': str(entries['social_links'].id), 'url': 'https://example.com/new'}],
        }, 1)
        self.service.confirm('test-confirmation', self.user_id)
        self.assert_saved_proposal(proposal)
        self.assertEqual(self.db.scalar(select(ApplicantSkill.name).where(ApplicantSkill.id == untouched_id)), 'SQL')
        self.assertEqual(self.writer.obtain_profile_by_user_id(self.user_id).version, 2)

    def test_deletion_and_addition_in_the_same_section_preserve_other_users(self):
        self.seed_profile()
        entries = self.seed_children()
        other_user = uuid.uuid4()
        self.seed_profile(other_user)
        others = self.seed_children(other_user)
        second_skill = self.writer.add_skill_profile({'id': str(uuid.uuid4()), 'name': 'SQL'}, self.user_id)
        self.db.commit()
        data = {section: [{'id': str(entry.id)}] for section, entry in entries.items()}
        data['skills'] += [{'id': str(second_skill.id)}, {'name': 'Rust'}]
        proposal = self.prepare(data, 1)
        self.service.confirm('test-confirmation', self.user_id)
        self.assert_saved_proposal(proposal)
        self.assertEqual(list(self.db.scalars(select(ApplicantSkill.name).where(ApplicantSkill.user_id == self.user_id))), ['Rust'])
        for section, entry in others.items():
            model = type(entry)
            self.assertIsNotNone(self.db.scalar(select(model).where(model.id == entry.id)))

    def test_database_change_after_preview_rejects_confirmation_before_writing(self):
        profile = self.seed_profile()
        self.db.commit()
        self.prepare({'profile': {'first_name': 'Reviewed'}}, 1)
        self.db.execute(update(ApplicantProfile).where(ApplicantProfile.id == profile.id).values(city='Concurrent City'))
        self.db.commit()
        with self.assertRaises(ProfileVersionConflictError):
            self.service.confirm('test-confirmation', self.user_id)
        self.db.refresh(profile)
        self.assertEqual(profile.first_name, 'Example')
        self.assertEqual(profile.city, 'Concurrent City')

    def test_failure_after_first_write_rolls_back_all_changes(self):
        profile = self.seed_profile()
        self.db.commit()
        self.prepare({'profile': {'first_name': 'Temporary'}, 'skills': [{'name': 'Rust'}]}, 1)
        with patch.object(self.service.profile_service.applicant_skill_repository, 'insert_skill',
                          side_effect=RuntimeError('simulated insert failure')):
            with self.assertRaisesRegex(RuntimeError, 'simulated insert failure'):
                self.service.confirm('test-confirmation', self.user_id)
        self.db.refresh(profile)
        self.assertEqual(profile.first_name, 'Example')
        self.assertEqual(profile.version, 1)
        self.assertEqual(list(self.db.scalars(select(ApplicantSkill))), [])


    def test_child_only_changes_advance_the_profile_version(self):
        self.seed_profile()
        self.db.commit()
        self.prepare({'skills': [{'name': 'Rust'}]}, 1)
        result = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(result['profile_version'], 2)
        self.assertEqual(result['saved']['skills'][0]['name'], 'Rust')

    def test_repeat_confirm_replays_sql_receipt_without_reading_redis(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        first = self.service.confirm('test-confirmation', self.user_id)
        self.store.get.side_effect = AssertionError('Replay must not reload the proposal')
        second = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(first, second)
        self.assertEqual(len(list(self.db.scalars(select(ApplicantProfile)))), 1)
        self.assertEqual(len(list(self.db.scalars(select(ProfileConfirmationReceipt)))), 1)

    def test_newer_draft_is_preserved_without_reporting_save_failure(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.drafts.delete_old_draft.return_value = 0
        result = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['cleanup']['draft'], 'newer_draft_preserved')
        self.store.update_status.assert_called_once()

    def test_cleanup_outage_does_not_undo_success_and_retry_only_repairs_cleanup(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.drafts.delete_old_draft.side_effect = DraftStorageError('Unavailable')
        self.store.update_status.side_effect = ConfirmationStorageError('Unavailable')
        first = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(first['status'], 'completed')
        self.assertEqual(first['cleanup'], {'draft': 'pending', 'confirmation': 'pending'})
        self.drafts.delete_old_draft.side_effect = None
        self.drafts.delete_old_draft.return_value = 2
        self.store.update_status.side_effect = None
        second = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(second['profile_version'], 1)
        self.assertEqual(second['cleanup']['draft'], 'already_absent')
        self.store.claim.assert_called_once()

    def test_receipt_insert_failure_rolls_back_profile_and_retains_draft(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        with patch.object(self.service.receipts, 'add', side_effect=RuntimeError('Receipt failed')):
            with self.assertRaisesRegex(RuntimeError, 'Receipt failed'):
                self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(list(self.db.scalars(select(ApplicantProfile))), [])
        self.assertEqual(list(self.db.scalars(select(ProfileConfirmationReceipt))), [])
        self.drafts.delete_old_draft.assert_not_called()
        self.store.update_status.assert_not_called()

    def test_failed_claim_prevents_all_sql_writes(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.store.claim.side_effect = DraftConflictError('Draft changed')
        with self.assertRaises(DraftConflictError):
            self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(list(self.db.scalars(select(ApplicantProfile))), [])
        self.assertEqual(list(self.db.scalars(select(ProfileConfirmationReceipt))), [])

    def test_processing_proposal_can_resume_after_rolled_back_worker(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.store.get.return_value['status'] = 'processing'
        result = self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(result['status'], 'completed')

    def test_cancel_preserves_draft_and_prevents_future_confirmation(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        first = self.service.cancel('test-confirmation', self.user_id)
        self.assertEqual(first['status'], 'cancelled')
        self.store.get.side_effect = AssertionError('Replay must use the receipt')
        self.assertEqual(self.service.cancel('test-confirmation', self.user_id), first)
        with self.assertRaises(ConfirmationValidationError):
            self.service.confirm('test-confirmation', self.user_id)
        self.assertEqual(list(self.db.scalars(select(ApplicantProfile))), [])
        self.drafts.delete_old_draft.assert_not_called()

    def test_completed_confirmation_cannot_be_cancelled(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.service.confirm('test-confirmation', self.user_id)
        with self.assertRaises(ConfirmationValidationError):
            self.service.cancel('test-confirmation', self.user_id)

    def test_receipt_is_scoped_to_authenticated_owner(self):
        self.prepare({'profile': preview_fixtures.valid_profile()}, None)
        self.service.confirm('test-confirmation', self.user_id)
        self.assertIsNone(self.service.receipts.get(uuid.uuid4(), 'test-confirmation'))


class ConfirmationApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ConfirmationSqlFlowTests('test_create_profile_and_all_sections_preserves_preview_ids')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare({'profile': preview_fixtures.valid_profile()}, None)
        app = FastAPI()
        app.include_router(router)
        register_exception_handlers(app)
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=self.fixture.user_id, username='Test')
        app.dependency_overrides[get_profile_draft_store] = lambda: self.fixture.drafts
        app.dependency_overrides[get_profile_confirmation_store] = lambda: self.fixture.store

        def database():
            with Session(self.fixture.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_confirm_response_and_retry(self):
        first = self.client.post('/profile/confirm/test-confirmation')
        self.assertEqual(first.status_code, 200, first.text)
        result = first.json()['data']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['profile_version'], 1)
        self.assertEqual(result['saved']['profile']['first_name'], 'Example')
        second = self.client.post('/profile/confirm/test-confirmation')
        self.assertEqual(second.json(), first.json())
        self.fixture.store.claim.assert_called_once()

    def test_cancel_prevents_confirm(self):
        response = self.client.post('/profile/cancel/test-confirmation')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['status'], 'cancelled')
        self.assertEqual(self.client.post('/profile/confirm/test-confirmation').status_code, 409)
        self.fixture.drafts.delete_old_draft.assert_not_called()

    def test_committed_save_with_cleanup_failure_still_returns_success(self):
        self.fixture.drafts.delete_old_draft.side_effect = DraftStorageError('Unavailable')
        response = self.client.post('/profile/confirm/test-confirmation')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['data']['cleanup']['draft'], 'pending')

    def test_another_user_cannot_execute_the_proposal(self):
        self.app.dependency_overrides[get_current_user] = lambda: UserResponse(id=uuid.uuid4(), username='Other')
        response = self.client.post('/profile/confirm/test-confirmation')
        self.assertEqual(response.status_code, 403, response.text)
        self.fixture.store.claim.assert_not_called()


class ConfirmationTransitionTests(unittest.TestCase):
    def setUp(self):
        self.redis = Mock(spec=Redis)
        self.store = ProfileConfirmationStore(self.redis)
        self.user_id, self.version = uuid.uuid4(), uuid.uuid4()

    def test_missing_confirmation_finalization_is_safe(self):
        self.redis.eval.return_value = [2]
        self.assertEqual(self.store.update_status(self.user_id, 'token', self.version), 2)

    def test_finalization_handles_every_return_code(self):
        for code, error in ((0, ConfirmationValidationError), (99, ConfirmationStorageError)):
            self.redis.eval.return_value = [code]
            with self.subTest(code=code), self.assertRaises(error):
                self.store.update_status(self.user_id, 'token', self.version)
        self.redis.eval.return_value = [1]
        self.assertEqual(self.store.update_status(self.user_id, 'token', self.version), 1)

    def test_claim_handles_expired_conflicting_and_changed_drafts(self):
        for code, error in ((2, ConfirmationNotFoundError), (0, ConfirmationValidationError),
                            (3, DraftConflictError)):
            self.redis.eval.return_value = [code]
            with self.subTest(code=code), self.assertRaises(error):
                self.store.claim(self.user_id, 'token', self.version)
        self.redis.eval.return_value = [1]
        self.store.claim(self.user_id, 'token', self.version)

    def test_draft_cleanup_preserves_all_three_outcomes(self):
        drafts = ProfileDraftStore(self.redis)
        for code in (0, 1, 2):
            self.redis.eval.return_value = [code]
            self.assertEqual(drafts.delete_old_draft(self.user_id, self.version), code)


@unittest.skipUnless(os.environ.get("PROFILE_DRAFT_REDIS_TEST_URL"), "Optional live Redis integration")
class ConfirmationReadRedisTests(unittest.TestCase):
    def setUp(self):
        self.redis = Redis.from_url(os.environ["PROFILE_DRAFT_REDIS_TEST_URL"], decode_responses=True,
                                    socket_connect_timeout=3, socket_timeout=3)
        self.addCleanup(self.redis.close)
        self.user_id = uuid.uuid4()
        self.drafts = ProfileDraftStore(self.redis)
        self.addCleanup(self.redis.delete, self.drafts.prefix + str(self.user_id))
        self.draft = ProfileDraftService(self.drafts).save_draft(
            self.user_id, SaveProfileDraftRequest(expected_version=None, data={}),
        )
        self.store = ProfileConfirmationStore(self.redis)
        self.token, _ = self.store.create(self.user_id, self.draft.version, json.dumps(payload(self.user_id, self.draft.version)))
        self.key = self.store.prefix + str(self.user_id) + ":" + self.token
        self.addCleanup(self.redis.delete, self.key)
        self.service = ConfirmationService(self.store, self.drafts, empty_database())

    def test_actual_preview_storage_shape_is_readable_and_valid(self):
        record = self.service.validate_confirmation(self.user_id, self.token)
        self.assertEqual(record.payload.draft_version, self.draft.version)
        self.assertEqual(record.status, "awaiting_confirmation")

    def test_live_draft_change_is_rejected(self):
        ProfileDraftService(self.drafts).save_draft(self.user_id, SaveProfileDraftRequest(expected_version=self.draft.version, data={}))
        with self.assertRaises(DraftConflictError):
            self.service.validate_confirmation(self.user_id, self.token)

    def test_confirmation_ttl_cannot_exceed_remaining_draft_lifetime(self):
        self.redis.expire(self.drafts.prefix + str(self.user_id), 30)
        with patch('modules.profile.confirmations.secrets.token_urlsafe', return_value=self.token + '-short'):
            token, expiry = self.store.create(self.user_id, self.draft.version,
                                             json.dumps(payload(self.user_id, self.draft.version)))
        key = self.store.prefix + str(self.user_id) + ':' + token
        self.addCleanup(self.redis.delete, key)
        ttl = self.redis.ttl(key)
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, 30)
        self.assertLessEqual(ttl, self.redis.ttl(self.drafts.prefix + str(self.user_id)))

    def test_live_token_collision_does_not_overwrite_existing_payload(self):
        before = self.redis.hgetall(self.key)
        with patch('modules.profile.confirmations.secrets.token_urlsafe', return_value=self.token):
            with self.assertRaises(ConfirmationStorageError):
                self.store.create(self.user_id, self.draft.version, '{"replacement":true}')
        self.assertEqual(self.redis.hgetall(self.key), before)

    def test_deleted_draft_cannot_create_another_confirmation(self):
        self.redis.delete(self.drafts.prefix + str(self.user_id))
        with self.assertRaises(DraftConflictError):
            self.store.create(self.user_id, self.draft.version, '{}')

    def test_live_claim_finalization_and_cleanup_preserve_ttl(self):
        before = self.redis.pttl(self.key)
        self.store.claim(self.user_id, self.token, self.draft.version)
        self.assertEqual(self.redis.hget(self.key, 'status'), 'processing')
        self.assertEqual(self.store.update_status(self.user_id, self.token, self.draft.version), 1)
        self.assertEqual(self.redis.hget(self.key, 'status'), 'completed')
        self.assertLessEqual(self.redis.pttl(self.key), before)
        self.assertEqual(self.drafts.delete_old_draft(self.user_id, self.draft.version), 1)
        self.assertEqual(self.drafts.delete_old_draft(self.user_id, self.draft.version), 2)
        self.redis.delete(self.key)
        self.assertEqual(self.store.update_status(self.user_id, self.token, self.draft.version), 2)

    def test_live_new_draft_prevents_claim_and_old_version_deletion(self):
        newer = ProfileDraftService(self.drafts).save_draft(
            self.user_id, SaveProfileDraftRequest(expected_version=self.draft.version, data={}),
        )
        with self.assertRaises(DraftConflictError):
            self.store.claim(self.user_id, self.token, self.draft.version)
        self.assertEqual(self.drafts.delete_old_draft(self.user_id, self.draft.version), 0)
        self.assertEqual(ProfileDraftService(self.drafts).get_draft(self.user_id).version, newer.version)


if __name__ == "__main__":
    unittest.main()
