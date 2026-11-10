from fastapi import Depends, FastAPI, Request
from typing import Annotated

from common.config import settings
from modules.auth.schemas import UserResponse
from modules.auth.sessions import SessionStore, get_session_store


def get_current_user(
        request: Request,
        session: Annotated[SessionStore, Depends(get_session_store)]
) -> UserResponse:
    token = request.cookies.get(settings.session_cookie_name)
    return session.get(token)

CurrentUser = Annotated[UserResponse, Depends(get_current_user)]