import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.exceptions import AppError
from common.responses import error_response

logger = logging.getLogger(__name__)

def register_exception_handlers(app: FastAPI):

    @app.exception_handler(AppError)
    async def handle_app_error(
        request: Request,
        exc: AppError
    ):
        # Authentication failures use HTTP 500 and numeric code 500 by project contract.
        auth = request.url.path.startswith("/auth/")
        content = error_response(
            str(exc), 500 if auth else exc.code,
            retryable=getattr(exc, "retryable", False),
        )
        if getattr(exc, "details", None) is not None:
            content["error"]["details"] = exc.details
        return JSONResponse(
            status_code=500 if auth else getattr(exc, "status_code", 400),
            content=content,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic errors include rejected input; never echo credentials back to clients.
        message = "Invalid request"
        if request.url.path == "/auth/login":
            message = "Login failed"
        elif exc.errors():
            message = exc.errors()[0]["msg"]
        auth = request.url.path.startswith("/auth/")
        return JSONResponse(
            status_code=500 if auth else 422,
            content=error_response(message, 500 if auth else 422),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Avoid logging SQL parameters, which can contain password hashes or credentials.
        logger.error("Request failed: %s %s (%s)", request.method, request.url.path, type(exc).__name__)
        return JSONResponse(status_code=500, content=error_response("Internal server error", retryable=True))
