import uuid
import re
import string

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(min_length=10, max_length=30, repr=False)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        allowed = string.ascii_letters + string.digits + string.punctuation
        if (any(char not in allowed for char in value)
                or not re.search(r"[A-Za-z]", value)
                or not re.search(r"[0-9]", value)
                or not any(char in string.punctuation for char in value)):
            raise ValueError("Password must contain English letters, digits, and ASCII punctuation, without spaces")
        # Preserve the exact password; trimming or case conversion changes credentials.
        return value


class UserRegister(LoginRequest):
    confirm_password: str = Field(repr=False)

    @model_validator(mode="after")
    def validate_confirmation(self) -> "UserRegister":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
