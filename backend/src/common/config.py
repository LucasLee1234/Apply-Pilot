import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import Field, field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class EnvVar:
    name: str
    description: str
    default: str | None = None
    aliases: tuple[str, ...] = ()

    def _lookup(self, environ: Mapping[str, str]) -> tuple[str, str] | None:
        env = os.environ if environ is None else environ
        for candidate in (self.name, *self.aliases):
            value = env.get(candidate.upper(), "").strip()
            if value:
                return candidate, value
        return None

    def optional(self, environ: Mapping[str, str] | None = None) -> str | None:
        found = self._lookup(environ)
        return found[1] if found else None

    def is_set(self, environ: Mapping[str, str] | None = None) -> bool:
        return self._lookup(environ) is not None

    def get(self, default: str | None = None, environ: Mapping[str, str] | None = None) -> str:
        value = self.optional(environ)
        if value is not None:
            return value
        elif default is not None :
            return default
        return self.default or ""


class Registry:
    def __init__(self) -> None:
        self._vars: dict[str, EnvVar] = {}

    def var(
            self,
            name: str,
            description: str,
            default: str | None = None,
    ) -> EnvVar:
        if name in self._vars:
            raise ValueError(f"{name} declared twice")
        var = EnvVar(name, description, default)
        self._vars[name] = var
        return var

    def __getattr__(self, name: str) -> EnvVar:
        try:
            return self.__dict__["_vars"][name]
        except KeyError:
            raise KeyError(f"undeclared environment variable {name}") from None


    def __getitem__(self, name: str) -> EnvVar:
        try:
            return self._vars[name]
        except KeyError:
            raise KeyError(f"undeclared environment variable {name}") from None

    def __contains__(self, name: str) -> bool:
        return name in self._vars


ENV = Registry()

ENV.var(name="logging_level", description="Logging level", default="INFO")
ENV.var(name="database_url", description="Database url", default="")
ENV.var(name="redis_url", description="Redis url", default="")
ENV.var(name="session_ttl_seconds", description="Session ttl seconds", default="36000")
ENV.var(name="session_cookie_name", description="Session cookie_name", default="session")
ENV.var(name="session_cookie_secure", description="Session cookie_secure", default="False")
ENV.var(name="profile_draft_ttl_seconds", description="Profile draft ttl seconds",default="604800")
ENV.var(name="profile_confirmation_ttl_seconds", description="Profile confirmation ttl seconds",default="900")

TIMEZONE_VALUES = {
    "timezone.utc": datetime.timezone.utc
}

class Settings(BaseSettings):
    logging_level: str = Field(default='INFO', description='Logging level')
    database_url: str = Field(default='', description='Database url')
    redis_url: str = Field(default='', description='Redis url')
    session_ttl_seconds: int = Field(default=36000, gt=0)
    session_cookie_name: str = Field(default='session', description='Session cookie')
    # Enable this in HTTPS deployments; plain HTTP development cannot send Secure cookies.
    session_cookie_secure: bool = False
    profile_draft_ttl_seconds: int = Field(default=604800, gt=0)
    profile_draft_max_bytes: int = Field(default=1048576, gt=0)
    profile_confirmation_ttl_seconds: int = Field(default=900, gt=0)
    app_timezone: datetime.timezone = Field(default=datetime.timezone.utc)
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / '.env',
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    @field_validator("app_timezone", mode="before")
    @classmethod
    def parse_timezone(cls, value):
        timezone = TIMEZONE_VALUES.get(value)
        if timezone is not None:
            return datetime.timezone.utc if timezone == 'timezone.utc' else datetime.timezone.utc
        elif value is not None and timezone is None:
            raise ValueError("Timezone is not accepted")
        return datetime.timezone.utc

settings = Settings()




