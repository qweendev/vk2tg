from typing import Any

import pytest

from vk2tg.render import (
    CAPTION_LIMIT,
    MESSAGE_LIMIT,
    Album,
    Animation,
    Document,
    Options,
    Poll,
    Sources,
    Text,
    render_post,
    render_text,
    should_skip,
    split_html,
)

NO_LINK = Options(source_link=False)


def photo(url: str, width: int = 100) -> dict[str, Any]:
    return {
        "type": "photo",
        "photo": {
            "sizes": [
                {"url": f"{url}?s", "width": 10, "height": 10},
                {"url": url, "width": width, "height": width},
            ]
        },
    }


def post(
    text: str = "", attachments: list[dict[str, Any]] | None = None, **extra: Any
) -> dict[str, Any]:
    return {"id": 5, "owner_id": -1, "text": text, "attachments": attachments or [], **extra}


@pytest.mark.parametrize(
    ("raw", "html"),
    [
        ("Привет, [id1|Павел]!", 'Привет, <a href="https://vk.com/id1">Павел</a>!'),
        ("[club42|Наша группа]", '<a href="https://vk.com/club42">Наша группа</a>'),
        ("[https://example.com|сайт]", '<a href="https://example.com">сайт</a>'),
        ("#новости@habr и #ещё", "#новости и #ещё"),
        ("a < b & c", "a &lt; b &amp; c"),
        ("[id1|<script>]", '<a href="https://vk.com/id1">&lt;script&gt;</a>'),
    ],
)
def test_render_text(raw: str, html: str) -> None:
    assert render_text(raw) == html


def test_text_only_post_with_source_link() -> None:
    assert render_post(post("Новость"), Sources(), Options()) == [
        Text('Новость\n\n<a href="https://vk.com/wall-1_5">VK</a>')
    ]


def test_photos_use_largest_size_and_carry_the_caption() -> None:
    messages = render_post(post("Фото", [photo("a"), photo("b")]), Sources(), NO_LINK)
    assert messages == [Album(["a", "b"], "Фото")]


def test_original_photo_url_wins() -> None:
    item = photo("small")
    item["photo"]["orig_photo"] = {"url": "orig"}
    assert render_post(post("", [item]), Sources(), NO_LINK) == [Album(["orig"])]


def test_more_than_ten_photos_split_into_albums() -> None:
    messages = render_post(post("x", [photo(str(n)) for n in range(12)]), Sources(), NO_LINK)
    assert [len(m.photos) for m in messages if isinstance(m, Album)] == [10, 2]
    assert isinstance(messages[0], Album)
    assert messages[0].caption == "x"


def test_long_text_goes_after_the_photos() -> None:
    text = "слово " * 300
    messages = render_post(post(text, [photo("a")]), Sources(), NO_LINK)
    assert len(text) > CAPTION_LIMIT
    assert messages[0] == Album(["a"])
    assert all(isinstance(m, Text) for m in messages[1:])


def test_gif_and_document() -> None:
    attachments = [
        {"type": "doc", "doc": {"url": "https://vk.com/doc1", "ext": "gif"}},
        {"type": "doc", "doc": {"url": "https://vk.com/doc2", "ext": "pdf"}},
    ]
    messages = render_post(post("Файлы", attachments), Sources(), NO_LINK)
    assert messages == [Animation("https://vk.com/doc1", "Файлы"), Document("https://vk.com/doc2")]


def test_video_and_link_become_links_in_text() -> None:
    attachments = [
        {"type": "video", "video": {"owner_id": -1, "id": 7, "title": "Обзор"}},
        {"type": "link", "link": {"url": "https://habr.com/a"}},
    ]
    [message] = render_post(post("Смотрите", attachments), Sources(), NO_LINK)
    assert message == Text(
        'Смотрите\n\n<a href="https://vk.com/video-1_7">Обзор</a>\nhttps://habr.com/a'
    )


def test_poll_comes_last() -> None:
    poll = {
        "type": "poll",
        "poll": {
            "question": "Чай или кофе?",
            "multiple": False,
            "answers": [{"text": "Чай"}, {"text": "Кофе"}],
        },
    }
    messages = render_post(post("Опрос", [poll]), Sources(), NO_LINK)
    assert messages == [Text("Опрос"), Poll("Чай или кофе?", ["Чай", "Кофе"], multiple=False)]


def test_repost_shows_the_original_author_and_its_media() -> None:
    original = {"owner_id": -99, "id": 1, "text": "Оригинал", "attachments": [photo("p")]}
    sources = Sources.from_response({"groups": [{"id": 99, "name": "Хабр"}], "profiles": []})
    messages = render_post(post("Интересно", copy_history=[original]), sources, NO_LINK)
    assert messages == [Album(["p"], "Интересно\n\n<b>Хабр</b>\n\nОригинал")]


@pytest.mark.parametrize(
    ("extra", "options", "skipped"),
    [
        ({"marked_as_ads": 1}, Options(), True),
        ({"donut": {"is_donut": True}}, Options(), True),
        ({"copy_history": [{"owner_id": 1}]}, Options(include_reposts=False), True),
        ({"copy_history": [{"owner_id": 1}]}, Options(), False),
        ({}, Options(), False),
    ],
)
def test_should_skip(extra: dict[str, Any], options: Options, skipped: bool) -> None:
    assert should_skip(post(**extra), options) is skipped


def test_split_keeps_paragraphs_and_tags_whole() -> None:
    paragraph = '<a href="https://vk.com/id1">Павел</a> ' + "текст " * 100
    html = "\n\n".join([paragraph] * 10)
    chunks = split_html(html, MESSAGE_LIMIT)
    assert all(len(chunk) <= MESSAGE_LIMIT for chunk in chunks)
    assert "\n\n".join(chunks) == html
    assert all(chunk.count("<a ") == chunk.count("</a>") for chunk in chunks)


def test_split_falls_back_to_words() -> None:
    chunks = split_html("слово " * 2000, MESSAGE_LIMIT)
    assert len(chunks) > 1
    assert all(len(chunk) <= MESSAGE_LIMIT for chunk in chunks)
