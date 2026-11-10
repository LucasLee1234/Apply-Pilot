import uuid
from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from common.database import get_db
from common.responses import success_response
from modules.auth.dependencies import get_current_user, CurrentUser
from modules.profile.service import ApplicantProfileService
from modules.profile.schemas import CompleteProfileResult, ProfileDraftResult, SaveProfileDraftRequest
from modules.profile.drafts import ProfileDraftService, ProfileDraftStore, get_profile_draft_store
from modules.profile.confirmations import ProfileConfirmationStore, get_profile_confirmation_store, ConfirmationService
from modules.profile.preview import ProfilePreviewService
from modules.profile.preview_schemas import PreviewProfileRequest, ProfilePreviewResult

router = APIRouter(prefix="/profile", tags=["Applicant_Profile"], dependencies=[Depends(get_current_user)])

@router.get("/", response_model=CompleteProfileResult)
def get_profile_by_id(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    profile_service = ApplicantProfileService(db)
    # Ownership comes from the validated session, never a client-supplied user ID.
    profile = profile_service.obtain_complete_profile_by_user_id(user_id=current_user.id)
    return success_response(profile)


@router.get("/draft", response_model=ProfileDraftResult, response_model_exclude_unset=True)
def get_profile_draft(
    current_user: CurrentUser,
    store: Annotated[ProfileDraftStore, Depends(get_profile_draft_store)],
):
    draft = ProfileDraftService(store).get_draft(current_user.id)
    return success_response(draft.model_dump(mode="json", exclude_unset=True) if draft else None)


@router.put("/draft", response_model=ProfileDraftResult, response_model_exclude_unset=True)
def save_profile_draft(
    request: SaveProfileDraftRequest, current_user: CurrentUser,
    store: Annotated[ProfileDraftStore, Depends(get_profile_draft_store)],
):
    draft = ProfileDraftService(store).save_draft(current_user.id, request)
    return success_response(draft.model_dump(mode="json", exclude_unset=True))


@router.post("/preview", response_model=ProfilePreviewResult)
def preview_profile_save(
    request: PreviewProfileRequest, current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    drafts: Annotated[ProfileDraftStore, Depends(get_profile_draft_store)],
    confirmations: Annotated[ProfileConfirmationStore, Depends(get_profile_confirmation_store)],
):
    proposal = ProfilePreviewService(db, drafts, confirmations).preview(current_user.id, request)
    return success_response(proposal)

@router.post("/confirm/{confirmation_id}")
def confirm_profile_save(
        confirmation_id: str,
        current_user: CurrentUser,
        db: Annotated[Session, Depends(get_db)],
        confirmations: Annotated[ProfileConfirmationStore, Depends(get_profile_confirmation_store)],
        drafts: Annotated[ProfileDraftStore, Depends(get_profile_draft_store)]
):
    result = ConfirmationService(store=confirmations, draft_store= drafts, db=db).confirm(confirmation_id=confirmation_id, user_id=current_user.id)
    return success_response(result)


@router.post("/cancel/{confirmation_id}")
def cancel_profile_save(
    confirmation_id: str, current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    confirmations: Annotated[ProfileConfirmationStore, Depends(get_profile_confirmation_store)],
    drafts: Annotated[ProfileDraftStore, Depends(get_profile_draft_store)],
):
    result = ConfirmationService(confirmations, drafts, db).cancel(confirmation_id, current_user.id)
    return success_response(result)
