import json
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from modules.profile.confirmations import ProfileConfirmationStore
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore
from modules.profile.exceptions import (
    DraftConflictError, DraftNotFoundError, ProfileValidationError, ProfileVersionConflictError,
)
from modules.profile.preview_schemas import PreviewProfileRequest, ProfileChange, ProfilePreviewResponse
from modules.profile.utils import SECTIONS, get_fingerprint, read_baseline
from modules.profile.validation import FormalProfileSnapshot


class ProfilePreviewService:
    def __init__(self, db: Session, drafts: ProfileDraftStore, confirmations: ProfileConfirmationStore):
        self.db = db
        self.drafts = ProfileDraftService(drafts)
        self.confirmations = confirmations

    def preview(self, user_id: uuid.UUID, request: PreviewProfileRequest) -> ProfilePreviewResponse:
        draft = self.drafts.get_draft(user_id)
        if draft is None:
            raise DraftNotFoundError("No draft found. Save a profile draft first.")
        if draft.version != request.draft_version:
            raise DraftConflictError("Draft changed. Reload it before previewing again.")

        current, baseline = read_baseline(self.db, user_id)
        base_version = current.version if current else None
        if base_version != request.expected_profile_version:
            raise ProfileVersionConflictError("Formal profile changed. Reload it before previewing again.")

        patch = draft.data.model_dump(exclude_unset=True)
        candidate = {"profile": {**baseline["profile"], **patch.get("profile", {})}}
        issues = []
        for section in SECTIONS:
            if section not in patch:
                candidate[section] = baseline[section]
                continue
            owned = {row["id"]: row for row in baseline[section]}
            # Child arrays are operations on saved records, not replacement lists.
            proposed_rows = dict(owned)
            seen_ids = set()
            next_order = max((row["sort_order"] for row in owned.values()), default=-1) + 1
            for index, entry in enumerate(patch[section]):
                entry_id = entry.get("id")
                content = {key: value for key, value in entry.items() if key != "id"}
                if entry_id is not None:
                    try:
                        entry_id = str(uuid.UUID(str(entry_id)))
                    except ValueError:
                        issues.append({"field": f"{section}.{index}.id", "message": "Enter a valid record UUID"})
                        continue
                    if entry_id not in owned:
                        issues.append({"field": f"{section}.{index}.id", "message": "Record does not belong to the current user's saved section"})
                        continue
                    if entry_id in seen_ids:
                        issues.append({"field": f"{section}.{index}.id", "message": "Duplicate record IDs in section operations"})
                        continue
                    seen_ids.add(entry_id)
                    if not content:
                        del proposed_rows[entry_id]
                        continue
                elif not content:
                    # Neither an ID nor editable fields means no operation.
                    continue
                # Freeze new IDs now so the displayed proposal and eventual save are identical.
                proposed_entry = {**owned.get(entry_id, {}), **content, "id": entry_id or str(uuid.uuid4())}
                if entry_id is None:
                    proposed_entry.setdefault("sort_order", next_order)
                    next_order += 1
                proposed_rows[proposed_entry["id"]] = proposed_entry
            candidate[section] = list(proposed_rows.values())
        if issues:
            raise ProfileValidationError(issues)
        try:
            proposed = FormalProfileSnapshot.model_validate(candidate)
        except ValidationError as exc:
            # Return field paths and messages without echoing unvalidated input or tracebacks.
            raise ProfileValidationError([
                {"field": ".".join(map(str, error["loc"])) or "profile",
                 "message": error["msg"]}
                for error in exc.errors()
            ]) from exc
        after = proposed.model_dump(mode="json")
        for section in SECTIONS:
            after[section].sort(key=lambda row: (row["sort_order"], row["id"]))
        proposed = FormalProfileSnapshot.model_validate(after)
        changes = self._changes(baseline, after)

        if not changes:
            latest = self.drafts.get_draft(user_id)
            if latest is None or latest.version != draft.version:
                raise DraftConflictError("Draft changed or expired. Reload it before previewing again.")
            return ProfilePreviewResponse(
                status="no_changes", confirmation_id=None, message="No changes to save.",
                draft_version=draft.version, base_profile_version=base_version,
                expires_at=None, changes=[], proposed=proposed,
            )

        fingerprint = get_fingerprint(
            current_id=str(current.id) if current else None, base_version=base_version, baseline=baseline,
        )
        payload = json.dumps({
            "user_id": str(user_id), "draft_version": str(draft.version),
            "base_profile_version": base_version, "base_snapshot_hash": fingerprint,
            "proposed": after, "changes": [change.model_dump(mode="json") for change in changes],
        }, separators=(",", ":"))
        confirmation_id, expires_at = self.confirmations.create(user_id, draft.version, payload)
        return ProfilePreviewResponse(
            status="awaiting_confirmation", confirmation_id=confirmation_id,
            message="Review these changes before confirming. Nothing has been saved to PostgreSQL.",
            draft_version=draft.version, base_profile_version=base_version,
            expires_at=expires_at, changes=changes, proposed=proposed,
        )

    @staticmethod
    def _changes(before: dict, after: dict) -> list[ProfileChange]:
        changes = []
        for field, value in after["profile"].items():
            previous = before["profile"].get(field)
            if previous != value:
                changes.append(ProfileChange(
                    field="profile." + field,
                    operation="add" if field not in before["profile"] else "update",
                    before=previous, after=value,
                ))
        for section in SECTIONS:
            previous = {row["id"]: row for row in before[section]}
            proposed = {row["id"]: row for row in after[section]}
            for entry_id, row in previous.items():
                if entry_id not in proposed:
                    changes.append(ProfileChange(field=f"{section}[{entry_id}]", operation="remove", before=row, after=None))
            for entry_id, row in proposed.items():
                if entry_id not in previous:
                    changes.append(ProfileChange(field=f"{section}[{entry_id}]", operation="add", before=None, after=row))
                    continue
                for field, value in row.items():
                    if value != previous[entry_id].get(field):
                        changes.append(ProfileChange(
                            field=f"{section}[{entry_id}].{field}", operation="update",
                            before=previous[entry_id].get(field), after=value,
                        ))
        return changes
