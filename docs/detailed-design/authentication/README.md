# Registration and Login: Initial Scope

## Confirmed Requirements

- Provide registration and login using a username and password in the initial version.
- Establish a stable user ID associated with the system account.
- At registration, generate the user ID and create an account record in a PostgreSQL table named `user`. This table manages each account's ID, username, and password hash; it must not store plaintext passwords.
- Use the same ID to associate Redis applicant drafts and the eventual formal applicant profile.
- After restarting or reopening the system and logging in, retrieve the user's unexpired Redis draft by that ID. Draft retention is seven days.
- Keep authentication accounts separate from applicant profile completeness. A registered account may exist while its applicant information is still only a Redis draft.

## Credential Boundary

Apply Pilot's own username/password authentication is separate from company or recruitment website login. Store a password hash rather than a plaintext system password. Do not store job-site login account information, passwords, or verification codes in applicant data or historical records.

## Username and Password Validation

| Input | Rules |
| --- | --- |
| Username | Non-empty, at most 20 characters, composed only of letters and digits. Spaces and other characters are not allowed. Case-sensitive and unique; duplicate registration of the same case-sensitive username is not allowed. |
| Password | 10-30 characters inclusive, containing at least one letter, one digit, and one special character. Exact character sets remain to be specified. |

Lengths exactly 10 or 30 are accepted. Username comparisons are case-sensitive. The precise accepted letter/digit and special-character sets remain to be designed.

Login failure must return a generic `Login failed` message using the shared response format, without separate user-not-found or password-mismatch messages.

## Redis Login Sessions

- The initial version permits only one active device login per user. Multi-device login is deferred, superseding the earlier shared multi-device session design. Store the active login session in Redis under the authenticated user's context; session data must not contain the password.
- Other system modules identify the current user through the session associated with the request or operation. Do not use one global current-user value shared across users.
- Logging out invalidates the corresponding session immediately.
- A session expires after 10 hours without authenticated user activity. Authenticated user operations and page access refresh the idle expiration to 10 hours from that activity. This supersedes the earlier one-hour timeout.
- If the session is missing, logged out, or expired, the operation must not treat it as an authenticated user session; the user must log in again to access protected functionality.
- Login sessions and applicant drafts have separate lifecycles: invalidating a session does not delete the user's seven-day profile draft or saved PostgreSQL data.

User identity must be established through successful authentication or a validated session, not a client-supplied user ID alone. Session identifiers must be unpredictable authentication credentials distinct from user IDs. Add rate limiting for repeated failed login attempts; exact thresholds remain to be designed.

A successful new login replaces the user's previous login session, immediately signing out the previous device. The client session identifier mechanism and transport remain to be designed. Whether background activity or polling refreshes the idle period will be clarified during that design.

## Pending Detailed Design

ID format, exact character sets, hashing implementation, session identifier transport, concurrency handling, and specific error codes have not yet been designed. Responses must follow the [Shared Response Format](../../design/response-format.md). Account persistence is confirmed as the PostgreSQL `user` table; exact column names, types, and constraints remain to be designed. No email registration, verification, or password recovery functionality is added by this document.

See [Applicant Inputs and Drafts](../personal-information/inputs.md) and [Technology Stack](../../design/technology-stack.md).
