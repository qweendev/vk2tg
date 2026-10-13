from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx

API_URL = "https://api.vk.com/method/"
API_VERSION = "5.199"
TOO_MANY_REQUESTS = 6
RETRIES = 3

_LINK_PREFIX = re.compile(r"^(?:https?://)?(?:m\.)?vk\.(?:com|ru)/")
_NUMERIC_COMMUNITY = re.compile(r"^(?:-|club|public|event)(\d+)$")


class VkError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"VK error {code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Wall:
    posts: list[dict[str, Any]]
    response: dict[str, Any]


def wall_owner(source: str) -> dict[str, str]:
    """Accept what people paste: a short name, club123, -123 or a full vk.com link."""
    name = _LINK_PREFIX.sub("", source.strip()).strip("/")
    if match := _NUMERIC_COMMUNITY.match(name):
        return {"owner_id": f"-{match.group(1)}"}
    return {"domain": name}


class VkClient:
    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._token = token

    async def wall(self, source: str, count: int = 20) -> Wall:
        response = await self.call("wall.get", **wall_owner(source), count=str(count), extended="1")
        return Wall(posts=response["items"], response=response)

    async def call(self, method: str, **params: str) -> dict[str, Any]:
        attempt = 0
        while True:
            reply = await self._client.post(
                API_URL + method,
                data={**params, "access_token": self._token, "v": API_VERSION},
            )
            reply.raise_for_status()
            body: dict[str, Any] = reply.json()
            error = body.get("error")
            if error is None:
                result: dict[str, Any] = body["response"]
                return result
            attempt += 1
            if error["error_code"] != TOO_MANY_REQUESTS or attempt == RETRIES:
                raise VkError(error["error_code"], error["error_msg"])
            await asyncio.sleep(attempt)
