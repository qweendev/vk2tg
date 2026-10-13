"""Turn a VK wall post into the messages that reproduce it in a Telegram channel."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from html import escape
from typing import Any

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
ALBUM_LIMIT = 10
POLL_OPTIONS_LIMIT = 10
POLL_QUESTION_LIMIT = 300
POLL_OPTION_LIMIT = 100

_MENTION = re.compile(r"\[(id|club|public|event)(\d+)\|([^\]]+)\]")
_LINK = re.compile(r"\[(https?://[^|\]]+)\|([^\]]+)\]")
_GROUP_HASHTAG = re.compile(r"(#[\w]+)@[\w.]+")
_MARKUP = re.compile(f"{_MENTION.pattern}|{_LINK.pattern}")


@dataclass(frozen=True, slots=True)
class Text:
    html: str


@dataclass(frozen=True, slots=True)
class Album:
    photos: list[str]
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class Animation:
    url: str
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    url: str
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class Poll:
    question: str
    options: list[str]
    multiple: bool


Message = Text | Album | Animation | Document | Poll


@dataclass(frozen=True, slots=True)
class Sources:
    """Names of communities and people mentioned in a wall response, keyed by VK owner id."""

    names: dict[int, str] = field(default_factory=dict)

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> Sources:
        names = {-group["id"]: group["name"] for group in response.get("groups", [])}
        names |= {
            person["id"]: f"{person['first_name']} {person['last_name']}"
            for person in response.get("profiles", [])
        }
        return cls(names)


@dataclass(frozen=True, slots=True)
class Options:
    include_reposts: bool = True
    source_link: bool = True


def should_skip(post: dict[str, Any], options: Options) -> bool:
    if post.get("marked_as_ads") or post.get("donut", {}).get("is_donut"):
        return True
    return bool(post.get("copy_history")) and not options.include_reposts


def render_post(post: dict[str, Any], sources: Sources, options: Options) -> list[Message]:
    original = (post.get("copy_history") or [None])[0]
    body = original or post
    attachments = body.get("attachments", [])

    parts = [render_text(post.get("text", ""))]
    if original is not None:
        author = sources.names.get(original["owner_id"])
        parts += [
            f"<b>{escape(author)}</b>" if author else "",
            render_text(original.get("text", "")),
        ]
    parts.append("\n".join(link for item in attachments if (link := _attachment_link(item))))
    if options.source_link:
        parts.append(f'<a href="https://vk.com/wall{post["owner_id"]}_{post["id"]}">VK</a>')
    text = "\n\n".join(part for part in parts if part)

    photos = [url for item in attachments if item["type"] == "photo" and (url := _photo_url(item))]
    media: list[Album | Animation | Document] = [
        Album(photos[start : start + ALBUM_LIMIT]) for start in range(0, len(photos), ALBUM_LIMIT)
    ]
    media += [_document(item["doc"]) for item in attachments if item["type"] == "doc"]

    messages: list[Message]
    if media and len(text) <= CAPTION_LIMIT:
        messages = [replace(media[0], caption=text or None), *media[1:]]
    else:
        messages = [*media, *(Text(chunk) for chunk in split_html(text, MESSAGE_LIMIT))]
    messages += [_poll(item["poll"]) for item in attachments if item["type"] == "poll"]
    return messages


def render_text(text: str) -> str:
    """VK wiki markup to Telegram HTML: mentions and inline links become anchors."""
    text = _GROUP_HASHTAG.sub(r"\1", text)
    parts: list[str] = []
    position = 0
    for match in _MARKUP.finditer(text):
        parts.append(escape(text[position : match.start()]))
        if match.group(2):
            kind, number, label = match.group(1), match.group(2), match.group(3)
            prefix = "id" if kind == "id" else "club"
            parts.append(f'<a href="https://vk.com/{prefix}{number}">{escape(label)}</a>')
        else:
            parts.append(f'<a href="{escape(match.group(4))}">{escape(match.group(5))}</a>')
        position = match.end()
    parts.append(escape(text[position:]))
    return "".join(parts).strip()


def split_html(html: str, limit: int) -> list[str]:
    """Split on paragraph, then line, then word boundaries without cutting through a tag."""
    if len(html) <= limit:
        return [html] if html else []
    for separator in ("\n\n", "\n", " "):
        pieces = html.split(separator)
        if len(pieces) == 1:
            continue
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            candidate = f"{current}{separator}{piece}" if current else piece
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = piece
        if current:
            chunks.append(current)
        if all(len(chunk) <= limit for chunk in chunks):
            return chunks
        return [part for chunk in chunks for part in split_html(chunk, limit)]
    return [html[start : start + limit] for start in range(0, len(html), limit)]


def _photo_url(item: dict[str, Any]) -> str | None:
    photo = item["photo"]
    if original := photo.get("orig_photo", {}).get("url"):
        return str(original)
    sizes = photo.get("sizes") or []
    if not sizes:
        return None
    largest = max(sizes, key=lambda size: size.get("width", 0) * size.get("height", 0))
    return str(largest["url"])


def _attachment_link(item: dict[str, Any]) -> str | None:
    match item["type"]:
        case "link":
            return escape(item["link"]["url"])
        case "video":
            video = item["video"]
            title = escape(video.get("title") or "Видео")
            return f'<a href="https://vk.com/video{video["owner_id"]}_{video["id"]}">{title}</a>'
        case _:
            return None


def _document(doc: dict[str, Any]) -> Animation | Document:
    return Animation(doc["url"]) if doc.get("ext") == "gif" else Document(doc["url"])


def _poll(poll: dict[str, Any]) -> Poll:
    options = [answer["text"][:POLL_OPTION_LIMIT] for answer in poll["answers"]]
    return Poll(
        question=poll["question"][:POLL_QUESTION_LIMIT],
        options=options[:POLL_OPTIONS_LIMIT],
        multiple=bool(poll.get("multiple", False)),
    )
