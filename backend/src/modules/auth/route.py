import uuid

from fastapi import APIRouter, Request, Response
from fastapi.params import Depends
from sqlalchemy.orm import Session
from typing import Annotated

from common.database import get_db
from common.config import settings
from common.responses import success_response
from modules.auth.exceptions import SessionRequiredError
from modules.auth.schemas import LoginRequest, UserRegister
from modules.auth.service import UserService
from modules.auth.sessions import SessionStore, get_session_store

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me")
def current_session(
    request: Request, response: Response,
    sessions: Annotated[SessionStore, Depends(get_session_store)],
):
    # Bootstrap the frontend once after reload; never cache user-specific state.
    response.headers["Cache-Control"] = "no-store"
    try:
        account = sessions.get(request.cookies.get(settings.session_cookie_name))
    except SessionRequiredError:
        return success_response(None)
    return success_response(account)


@router.post("/login")
def login(
    user: LoginRequest, response: Response,
    db: Annotated[Session, Depends(get_db)],
    sessions: Annotated[SessionStore, Depends(get_session_store)],
):
    account = UserService(db).login_user(user.username, user.password)
    token = sessions.create(account)
    # Omit Max-Age so Redis alone controls the sliding idle timeout.
    response.set_cookie(
        key=settings.session_cookie_name, value=token, httponly=True,
        secure=settings.session_cookie_secure, samesite="lax", path="/",
    )
    return success_response(account)

@router.get("/username/{user_id}")
def get_username(
    user_id: uuid.UUID, request: Request,
    db: Annotated[Session, Depends(get_db)],
    sessions: Annotated[SessionStore, Depends(get_session_store)],
):
    account = sessions.get(request.cookies.get(settings.session_cookie_name))
    # A UUID identifies a record; the session determines who may access it.
    if account.id != user_id:
        raise SessionRequiredError("Access denied")
    user_service = UserService(db)
    return success_response({"username": user_service.get_username_by_id(user_id)})

@router.post("/register")
def register(user: UserRegister, db: Annotated[Session, Depends(get_db)]):
    user_service = UserService(db)
    return success_response(user_service.register_user(user))


@router.post("/logout")
def logout(request: Request, response: Response, sessions: Annotated[SessionStore, Depends(get_session_store)]):
    sessions.delete(request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(
        settings.session_cookie_name, path="/", secure=settings.session_cookie_secure,
        httponly=True, samesite="lax",
    )
    return success_response(None)
