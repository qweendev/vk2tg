from collections.abc import AsyncIterator
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vk2tg.config import Route
from vk2tg.publish import ChatId, Publisher
from vk2tg.relay import Relay
from vk2tg.render import Message, Text
from vk2tg.state import Base, State
from vk2tg.vk import VkClient, Wall

ROUTE = Route(vk="habr", telegram="@mirror", source_link=False)


class FakeVk(VkClient):
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def wall(self, source: str, count: int = 20) -> Wall:
        return Wall(posts=list(self.posts), response={"items": self.posts})


class FakePublisher(Publisher):
    def __init__(self) -> None:
        self.sent: list[tuple[ChatId, Message]] = []
        self.reject: set[str] = set()

    async def publish(self, chat_id: ChatId, message: Message) -> None:
        if isinstance(message, Text) and message.html in self.reject:
            raise TelegramBadRequest(SendMessage(chat_id=chat_id, text=""), "bad")
        self.sent.append((chat_id, message))


def vk_post(post_id: int, text: str, **extra: Any) -> dict[str, Any]:
    return {"id": post_id, "owner_id": -1, "text": text, "attachments": [], **extra}


@pytest.fixture
async def state() -> AsyncIterator[State]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield State(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


def texts(publisher: FakePublisher) -> list[str]:
    return [m.html for _, m in publisher.sent if isinstance(m, Text)]


async def test_first_run_does_not_flood_the_channel(state: State) -> None:
    vk, publisher = FakeVk(), FakePublisher()
    vk.posts = [vk_post(3, "старый"), vk_post(2, "ещё старее")]
    relay = Relay(vk, publisher, state, [ROUTE], interval=0)

    assert await relay.sync(ROUTE) == 0
    assert publisher.sent == []
    assert await state.last_post_id(ROUTE.key) == 3


async def test_new_posts_go_out_oldest_first_and_only_once(state: State) -> None:
    vk, publisher = FakeVk(), FakePublisher()
    relay = Relay(vk, publisher, state, [ROUTE], interval=0)
    vk.posts = [vk_post(1, "начало")]
    await relay.sync(ROUTE)

    vk.posts = [vk_post(1, "закреп", is_pinned=1), vk_post(3, "третий"), vk_post(2, "второй")]
    assert await relay.sync(ROUTE) == 2
    assert await relay.sync(ROUTE) == 0
    assert texts(publisher) == ["второй", "третий"]
    assert {chat for chat, _ in publisher.sent} == {"@mirror"}


async def test_ads_are_skipped_but_remembered(state: State) -> None:
    vk, publisher = FakeVk(), FakePublisher()
    relay = Relay(vk, publisher, state, [ROUTE], interval=0)
    vk.posts = [vk_post(1, "начало")]
    await relay.sync(ROUTE)

    vk.posts = [vk_post(2, "реклама", marked_as_ads=1)]
    assert await relay.sync(ROUTE) == 0
    assert await state.last_post_id(ROUTE.key) == 2


async def test_post_rejected_by_telegram_is_not_retried_forever(state: State) -> None:
    vk, publisher = FakeVk(), FakePublisher()
    relay = Relay(vk, publisher, state, [ROUTE], interval=0)
    vk.posts = [vk_post(1, "начало")]
    await relay.sync(ROUTE)

    publisher.reject = {"сломанный"}
    vk.posts = [vk_post(2, "сломанный"), vk_post(3, "нормальный")]
    assert await relay.sync(ROUTE) == 1
    assert await relay.sync(ROUTE) == 0
    assert texts(publisher) == ["нормальный"]
