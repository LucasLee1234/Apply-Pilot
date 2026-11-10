from common.exceptions import AppError


class ProfileNotFoundError(AppError):
    code = "ProfileNotFoundError"

class ProfileUpdateError(AppError):
    code = "ProfileUpdateError"
    status_code = 503

class ProfileCreateError(AppError):
    code = "ProfileCreateError"
    status_code = 400


class ProfileNotMatchedError(AppError):
    code = "ProfileNotMatchedError"
    status_code = 404

class DraftConflictError(AppError):
    code = "DRAFT_VERSION_CONFLICT"
    status_code = 409


class DraftTooLargeError(AppError):
    code = "DRAFT_TOO_LARGE"
    status_code = 413


class DraftStorageError(AppError):
    code = "DRAFT_STORAGE_UNAVAILABLE"
    status_code = 503
    retryable = True


class DraftNotFoundError(AppError):
    code = "PROFILE_DRAFT_NOT_FOUND"
    status_code = 404


class ProfileVersionConflictError(AppError):
    code = "PROFILE_VERSION_CONFLICT"
    status_code = 409


class ProfileValidationError(AppError):
    code = "PROFILE_VALIDATION_FAILED"
    status_code = 422

    def __init__(self, details: list[dict[str, str]]):
        super().__init__("Correct the listed fields before saving the profile.")
        self.details = details


class ConfirmationStorageError(AppError):
    code = "PROFILE_CONFIRMATION_UNAVAILABLE"
    status_code = 503
    retryable = True

class ConfirmationValidationError(AppError):
    code = "PROFILE_CONFIRMATION_VALIDATION_FAILED"
    status_code = 409


class ConfirmationNotFoundError(AppError):
    code = "PROFILE_CONFIRMATION_NOT_FOUND"
    status_code = 404


class ConfirmationOwnershipError(AppError):
    code = "PROFILE_CONFIRMATION_FORBIDDEN"
    status_code = 403

class ApplicantSkillCreateError(AppError):
    code = "ApplicantSkillCreateError"
    status_code = 400


class WorkExperienceCreateError(AppError):
    code = "WorkExperienceCreateError"
    status_code = 400
