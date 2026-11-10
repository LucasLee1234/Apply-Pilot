# Apply Pilot backend

Run from this directory with Python 3.11 or later. Install dependencies with `uv sync`.

Configure `src/.env` with `DATABASE_URL` (a `postgresql+psycopg://` URL) and
`REDIS_URL`. The account model uses the existing `public.users` table.
The matching initialization reference is `../database/schema/users.sql`.
It creates a new table and must not be rerun against the existing deployment.
Updating the reference does not apply schema changes or migrate account records.

Start the API in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Registration requires `username`, `password`, and `confirm_password`.
Username: 1-20 ASCII letters or digits. Password: 10-30 characters containing
English letters, digits, and ASCII punctuation, without spaces. Passwords and
confirmation values are never returned in business responses.

Login verifies Argon2id credentials and sets an HttpOnly, SameSite=Lax session
Cookie. Redis stores one active session per account, with a sliding 10-hour idle
timeout. A new login invalidates the old session; logout cannot invalidate a
newer session from another device. Set `SESSION_COOKIE_SECURE=true` over HTTPS.
The Cookie name is configured by `SESSION_COOKIE_NAME` and defaults to `session`.
The browser must include credentials when calling the API from the frontend.
The allowed development frontend origin is `http://localhost:3000`.

Authentication endpoints use the shared `success`, `data`, and `error` response
envelope. Per the existing project contract, failures use HTTP 500 and numeric
error code 500. Registration does not create a login session.

`GET /profile/` requires the session Cookie and reads the authenticated user's
complete structured profile. Its success envelope contains `data.profile`,
`data.work_experiences`, `data.education_entries`, `data.social_links`, and
`data.skills`. Child lists are sorted by `sort_order` and `id`, and are empty
arrays when no entries exist. UUIDs and dates are serialized as strings; GPA is
serialized as a decimal string to preserve precision, or null when absent.

The endpoint takes its user ID from the validated session, not request input.
A missing base profile raises `ProfileNotFoundError`; under the current shared
non-auth error mapping, this returns HTTP 400 with the common failure envelope.
Session failures on this route also currently return HTTP 400. This change does
not alter the authentication module's existing status-code contract. Profile
creation and edits, including child-record deletion, use draft/preview/confirm;
direct mutation endpoints and Agent Tool wrappers are not provided.

`GET /profile/draft` retrieves the current user's incomplete Redis draft (or null).
`PUT /profile/draft` replaces it with `{"expected_version": null, "data": {...}}`
on first creation. Subsequent saves require the opaque UUID version returned by
the last read/save. Conflicts return 409; Redis failures return retryable 503.
Drafts expire seven days after creation; reads and edits do not extend that TTL.
Invalid business values can be retained, but unknown fields and credential fields
are rejected. No PostgreSQL records are created or modified. See the
[draft API specification](../docs/detailed-design/personal-information/draft-storage.md).

`POST /profile/preview` accepts `draft_version` (the draft UUID token) and
`expected_profile_version` (the current SQL integer version, or null for first
creation). It validates and compares the draft without changing PostgreSQL.
Invalid fields return 422 with `error.details`. A valid changed proposal returns
`awaiting_confirmation`, exact changes, normalized contents, and a pending
`confirmation_id` valid for at most 15 minutes. Unchanged data returns
`no_changes` with no confirmation token. Omitted fields/sections retain saved
values. Child arrays apply individual operations: ID only deletes that record,
ID plus editable fields updates it, and editable fields without an ID add a record.
Empty arrays and empty entries preserve saved records; omitted records are retained.
See the [preview specification](../docs/detailed-design/personal-information/preview-save.md).
`POST /profile/confirm/{confirmation_id}` commits the approved changes and a
durable SQL receipt in one transaction. It returns `status: "completed"`, the
approved `draft_version`, the resulting `profile_version`, and the complete
profile under `saved`. PostgreSQL transaction-level advisory locks serialize
confirm/cancel operations for each user, including first-profile creation. The
formal baseline is rechecked under the lock; child-only changes advance the
profile version too. Repeating the same confirmation returns its saved receipt
without writing again, even if Redis state has expired or disappeared.

Post-commit Redis cleanup is reported independently in `cleanup.confirmation`
and `cleanup.draft`. A newer draft is preserved. Redis cleanup failures return
`pending` without converting a committed save into failure; repeating confirm
retries cleanup. No background cleanup worker is implemented. A `processing`
proposal without a receipt can resume after acquiring the SQL lock, so a worker
crash or SQL rollback does not permanently consume the approval.

`POST /profile/cancel/{confirmation_id}` records cancellation without deleting
the draft or changing formal data. Repeated cancellation is safe; cancelled
proposals cannot be confirmed, and completed writes cannot be cancelled.

**Schema prerequisite:** from `backend/`, run
`uv run python -B ../database/create_profile_tables.py` to create the missing
`public.profile_confirmation_receipts` table before using confirm/cancel. This
preserves existing tables and data. See the [database guide](../database/README.md).

Run the isolated regression suite in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
$env:DATABASE_URL = 'sqlite://'
$env:REDIS_URL = 'redis://localhost:6379/0'
$env:APP_TIMEZONE = 'timezone.utc'
uv run python -B -m unittest discover -s test -p 'test_*.py' -v
```

The suite uses mocked authentication storage and in-memory SQLite profile data,
with simulated sessions. Redis Lua behavior and PostgreSQL
constraints still need integration testing against disposable service instances.
The design's configurable failed-login rate limiter is not implemented yet.

For opt-in service integration, set `PROFILE_DRAFT_REDIS_TEST_URL` to a disposable
Redis database to exercise the actual Lua scripts. Set
`PROFILE_CONFIRMATION_POSTGRES_TEST_URL` to a disposable PostgreSQL database for
the concurrency tests in `test_confirmation_postgres.py`; those tests create and
drop only their own generated schema, without using public application tables.
Enabling both URLs also runs combined real-service create/edit/delete, replay,
rollback/retry, and cancellation tests in that file.
SQLite tests validate transactions and replay behavior, but do not validate
PostgreSQL advisory locks or concurrent row locking.
