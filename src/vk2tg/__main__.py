from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vk2tg.config import Settings, load_routes
from vk2tg.publish import Publisher
from vk2tg.relay import Relay
from vk2tg.state import Base, State
from vk2tg.vk import VkClient


async def main() -> None:
    settings = Settings()
    routes = load_routes(settings.routes_file)

    database = make_url(settings.database_url)
    if database.get_backend_name() == "sqlite" and database.database:
        Path(database.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(database)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    bot = Bot(
        settings.telegram_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            relay = Relay(
                VkClient(client, settings.vk_token.get_secret_value()),
                Publisher(bot),
                State(async_sessionmaker(engine, expire_on_commit=False)),
                routes,
                settings.interval,
            )
            await relay.run()
    finally:
        await bot.session.close()
        await engine.dispose()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())


if __name__ == "__main__":
    run()
