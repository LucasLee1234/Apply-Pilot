from typing import Any

from fastapi.encoders import jsonable_encoder


def success_response(data: Any) -> dict:
    return {"success": True, "data": jsonable_encoder(data), "error": None}


def error_response(message: str, code: int | str = 500, retryable: bool = False) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "retryable": retryable},
    }
