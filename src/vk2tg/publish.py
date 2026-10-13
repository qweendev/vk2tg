from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InputMediaPhoto, InputPollOption, LinkPreviewOptions

from vk2tg.render import Album, Animation, Document, Message, Poll, Text

ChatId = int | str


class Publisher:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def publish(self, chat_id: ChatId, message: Message) -> None:
        try:
            await self._send(chat_id, message)
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after)
            await self._send(chat_id, message)

    async def _send(self, chat_id: ChatId, message: Message) -> None:
        bot = self._bot
        match message:
            case Text(html):
                await bot.send_message(
                    chat_id, html, link_preview_options=LinkPreviewOptions(prefer_large_media=True)
                )
            case Album([photo], caption):
                await bot.send_photo(chat_id, photo, caption=caption)
            case Album(photos, caption):
                await bot.send_media_group(
                    chat_id,
                    [
                        InputMediaPhoto(media=url, caption=caption if index == 0 else None)
                        for index, url in enumerate(photos)
                    ],
                )
            case Animation(url, caption):
                await bot.send_animation(chat_id, url, caption=caption)
            case Document(url, caption):
                await bot.send_document(chat_id, url, caption=caption)
            case Poll(question, options, multiple):
                await bot.send_poll(
                    chat_id,
                    question,
                    [InputPollOption(text=option) for option in options],
                    allows_multiple_answers=multiple,
                )
