from common.exceptions import AppError


class UserNotFoundError(AppError):
    code = 'UserNotFoundError'

class UserExistsError(AppError):
    code = 'UserExistsError'


class LoginFailedError(AppError):
    code = 'LoginFailedError'


class SessionRequiredError(AppError):
    code = 'SessionRequiredError'
