from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VK2TG_", env_file=".env")

    vk_token: SecretStr
    telegram_token: SecretStr
    routes_file: Path = Path("routes.toml")
    database_url: str = "sqlite+aiosqlite:///data/vk2tg.db"
    interval: int = Field(default=60, ge=10)


class Route(BaseModel):
    vk: str
    telegram: int | str
    reposts: bool = True
    source_link: bool = True

    @property
    def key(self) -> str:
        return f"{self.vk} -> {self.telegram}"


class RoutesFile(BaseModel):
    route: list[Route] = Field(min_length=1)


def load_routes(path: Path) -> list[Route]:
    with path.open("rb") as file:
        return RoutesFile.model_validate(tomllib.load(file)).route
