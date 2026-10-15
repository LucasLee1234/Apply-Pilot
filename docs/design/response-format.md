# Shared Response Format

## 1. Scope

Business module operation results, backend JSON API responses, and agent tool results must use this common envelope. Operation-specific data and error codes will be defined during detailed design. This does not define binary PDF/file responses or an unselected streaming protocol.

## 2. Success

```json
{
  "success": true,
  "data": {
    "id": 123,
    "name": "John",
    "email": "john@example.com"
  },
  "error": null
}
```

The data object above is the project owner's example, not a finalized profile schema or ID type. Each operation defines its own result payload under `data`.

## 3. Failure

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User does not exist",
    "retryable": false
  }
}
```

The error above is an example, not the required login failure response. Login failure uses a generic `Login failed` message; its specific code remains to be selected.

| Field | Meaning |
| --- | --- |
| `success` | Boolean indicating whether the operation succeeded. |
| `data` | Operation-specific result on success; `null` on failure. |
| `error` | `null` on success; error object on failure. |
| `error.code` | Machine-readable error identifier. |
| `error.message` | Explanation of the failure. |
| `error.retryable` | Boolean indicating whether the failed operation can be retried. This does not authorize automatic retries or bypass user approval. |

## 4. Waiting for User Confirmation

A successfully processed operation may require user confirmation before a formal change is made. In this case, `success: true` means the check completed successfully, not that the proposed change was saved. Use `data.status: "awaiting_confirmation"` to make the distinction explicit.

```json
{
  "success": true,
  "data": {
    "status": "awaiting_confirmation",
    "confirmation_id": "confirm_001",
    "message": "Confirm replacing the saved email.",
    "changes": [
      {
        "field": "default_email",
        "old_value": "old@example.com",
        "new_value": "new@example.com"
      }
    ]
  },
  "error": null
}
```

| Data Field | Meaning |
| --- | --- |
| `status` | `awaiting_confirmation` indicates that the operation is waiting for the user rather than having completed the change. |
| `confirmation_id` | Identifies the specific pending operation. The example does not prescribe an ID generation format. |
| `message` | Explains what the user is being asked to confirm. |
| `changes` | Proposed changes for the user to review. |
| `changes[].field` | Field affected by a proposed change. |
| `changes[].old_value` | Previously saved value. |
| `changes[].new_value` | Proposed replacement value. |

The frontend must display the proposal and provide confirmation and cancellation actions. An agent receiving this response must pause and wait for the user; it must not approve on the user's behalf.

## 5. Confirmation Submission and Result

The confirmation submission is an input payload, not a result envelope:

```json
{
  "confirmation_id": "confirm_001",
  "decision": "approve"
}
```

The backend must resolve the pending operation belonging to the authenticated user and its corresponding proposed contents. It must recheck data and conflicts before saving. A confirmation identifier alone does not authorize another user's operation.

Bind approval to the exact displayed proposal and relevant data version. Enforce approval server-side; agent tools cannot fabricate user approval. Changed proposals require fresh confirmation. Each confirmation executes its operation at most once and becomes unusable after completion, cancellation, or expiration. Exact expiration duration and repeat-request response payloads remain to be designed.

After successful saving, return the updated contents with `data.status: "completed"`:

```json
{
  "success": true,
  "data": {
    "status": "completed",
    "default_email": "new@example.com"
  },
  "error": null
}
```

User cancellation must leave formal information unchanged. The exact cancellation input and result payload remain to be designed. If saving fails, return the existing failure envelope and retain the draft. If rechecking reveals another unresolved conflict, obtain the user's decision rather than silently saving a different change.

## 6. Current Boundaries

No additional top-level envelope fields are introduced. Confirmation state is expressed inside `data`. HTTP status mapping, validation error details, confirmation expiration and storage, cancellation payloads, and other individual operations' payloads remain to be designed. Any later extension must preserve the agreed envelope unless the project owner approves changing it.
