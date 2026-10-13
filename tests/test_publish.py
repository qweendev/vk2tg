from collections.abc import AsyncGenerator
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import (
    SendAnimation,
    SendMediaGroup,
    SendMessage,
    SendPhoto,
    SendPoll,
    TelegramMethod,
)
from aiogram.methods.base import TelegramType

from vk2tg.publish import Publisher
from vk2tg.render import Album, Animation, Poll, Text


class RecordingSession(BaseSession):
    def __init__(self, flood_once: bool = False) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._flood_once = flood_once

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109  signature comes from BaseSession
    ) -> TelegramType:
        if self._flood_once:
            self._flood_once = False
            raise TelegramRetryAfter(method, "Flood control", retry_after=0)
        self.calls.append(method)
        return None  # type: ignore[return-value]

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes]:
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        return None


async def test_each_message_kind_maps_to_its_method() -> None:
    session = RecordingSession()
    publisher = Publisher(Bot("42:TEST", session=session))

    await publisher.publish("@c", Text("привет"))
    await publisher.publish("@c", Album(["a"], "подпись"))
    await publisher.publish("@c", Album(["a", "b"], "подпись"))
    await publisher.publish("@c", Animation("g"))
    await publisher.publish("@c", Poll("Да?", ["да", "нет"], multiple=True))

    kinds = [type(call) for call in session.calls]
    assert kinds == [SendMessage, SendPhoto, SendMediaGroup, SendAnimation, SendPoll]
    album = session.calls[2]
    assert isinstance(album, SendMediaGroup)
    assert [item.caption for item in album.media] == ["подпись", None]
    poll = session.calls[4]
    assert isinstance(poll, SendPoll)
    assert poll.allows_multiple_answers is True


async def test_waits_out_flood_control() -> None:
    session = RecordingSession(flood_once=True)
    await Publisher(Bot("42:TEST", session=session)).publish("@c", Text("привет"))
    assert len(session.calls) == 1
