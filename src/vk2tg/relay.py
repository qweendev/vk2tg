from __future__ import annotations

import asyncio
import logging

import httpx
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from vk2tg.config import Route
from vk2tg.publish import Publisher
from vk2tg.render import Options, Sources, render_post, should_skip
from vk2tg.state import State
from vk2tg.vk import VkClient, VkError

log = logging.getLogger(__name__)


class Relay:
    def __init__(
        self, vk: VkClient, publisher: Publisher, state: State, routes: list[Route], interval: float
    ) -> None:
        self._vk = vk
        self._publisher = publisher
        self._state = state
        self._routes = routes
        self._interval = interval

    async def run(self) -> None:
        while True:
            for route in self._routes:
                try:
                    await self.sync(route)
                except (VkError, httpx.HTTPError, TelegramAPIError) as error:
                    log.warning("%s: %s", route.key, error)
            await asyncio.sleep(self._interval)

    async def sync(self, route: Route) -> int:
        """Publish posts that appeared since the last run and return how many went out."""
        wall = await self._vk.wall(route.vk)
        newest = max((post["id"] for post in wall.posts), default=None)
        last = await self._state.last_post_id(route.key)
        if last is None:
            if newest is not None:
                await self._state.save(route.key, newest)
            log.info("%s: watching from post %s, older posts are skipped", route.key, newest)
            return 0

        options = Options(include_reposts=route.reposts, source_link=route.source_link)
        sources = Sources.from_response(wall.response)
        published = 0
        for post in sorted((p for p in wall.posts if p["id"] > last), key=lambda p: p["id"]):
            if not should_skip(post, options):
                try:
                    for message in render_post(post, sources, options):
                        await self._publisher.publish(route.telegram, message)
                    published += 1
                except TelegramBadRequest as error:
                    # Telegram will reject this post again on every retry, so move past it.
                    log.error("%s: post %s rejected by Telegram: %s", route.key, post["id"], error)
            await self._state.save(route.key, post["id"])
        return published
