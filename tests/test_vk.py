import httpx
import pytest
import respx

from vk2tg.vk import API_URL, VkClient, VkError, wall_owner


@pytest.mark.parametrize(
    ("source", "params"),
    [
        ("habr", {"domain": "habr"}),
        ("https://vk.com/habr/", {"domain": "habr"}),
        ("m.vk.com/club123", {"owner_id": "-123"}),
        ("public5", {"owner_id": "-5"}),
        ("-77", {"owner_id": "-77"}),
        ("https://vk.ru/id1", {"domain": "id1"}),
    ],
)
def test_wall_owner(source: str, params: dict[str, str]) -> None:
    assert wall_owner(source) == params


@respx.mock
async def test_retries_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr("vk2tg.vk.asyncio.sleep", instant)
    route = respx.post(API_URL + "wall.get").mock(
        side_effect=[
            httpx.Response(200, json={"error": {"error_code": 6, "error_msg": "Too many"}}),
            httpx.Response(200, json={"response": {"count": 1, "items": [{"id": 1}]}}),
        ]
    )
    async with httpx.AsyncClient() as client:
        wall = await VkClient(client, "token").wall("habr")
    assert wall.posts == [{"id": 1}]
    assert route.call_count == 2
    assert b"domain=habr" in route.calls.last.request.content


@respx.mock
async def test_other_errors_are_raised() -> None:
    respx.post(API_URL + "wall.get").respond(
        200, json={"error": {"error_code": 15, "error_msg": "Access denied"}}
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(VkError) as error:
            await VkClient(client, "token").wall("private_group")
    assert error.value.code == 15
