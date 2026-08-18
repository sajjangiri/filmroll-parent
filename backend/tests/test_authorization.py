"""Who may do what, and to which film."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth, join, make_film

pytestmark = pytest.mark.integration


async def test_guest_token_is_scoped_to_one_film(client: AsyncClient, future):
    """A guest at one event must not be able to act inside another."""
    code_a, _ = await make_film(client, closes_at=future, reveal_at=future, title="A")
    code_b, _ = await make_film(client, closes_at=future, reveal_at=future, title="B")
    token_a = await join(client, code_a)

    crossed = await client.post(
        f"/v1/films/{code_b}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(token_a),
    )
    assert crossed.status_code == 403


async def test_host_token_is_scoped_to_one_film(client: AsyncClient, future):
    code_a, host_a = await make_film(client, closes_at=future, reveal_at=future, title="A")
    code_b, _ = await make_film(client, closes_at=future, reveal_at=future, title="B")

    crossed = await client.post(f"/v1/films/{code_b}/reveal", headers=auth(host_a))
    assert crossed.status_code == 403


async def test_guest_cannot_use_host_endpoints(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    guest = await join(client, code)

    reveal = await client.post(f"/v1/films/{code}/reveal", headers=auth(guest))
    hide = await client.post(
        f"/v1/films/{code}/shots/{uuid.uuid4()}/hide", headers=auth(guest)
    )
    assert reveal.status_code == 403
    assert hide.status_code == 403


async def test_host_token_is_not_accepted_as_a_guest(client: AsyncClient, future):
    code, host_token = await make_film(client, closes_at=future, reveal_at=future)
    reserved = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(host_token),
    )
    assert reserved.status_code == 403


async def test_anonymous_requests_are_rejected(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)

    assert (await client.post(f"/v1/films/{code}/reveal")).status_code == 401
    assert (
        await client.post(
            f"/v1/films/{code}/shots/reserve", json={"shot_id": str(uuid.uuid4())}
        )
    ).status_code == 401


async def test_tampered_token_is_rejected(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    token = await join(client, code)

    # Flip the final character of the signature.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    response = await client.post(
        f"/v1/films/{code}/shots/reserve",
        json={"shot_id": str(uuid.uuid4())},
        headers=auth(tampered),
    )
    assert response.status_code == 401


async def test_garbage_token_is_rejected(client: AsyncClient, future):
    code, _ = await make_film(client, closes_at=future, reveal_at=future)
    response = await client.post(f"/v1/films/{code}/reveal", headers=auth("not-a-jwt"))
    assert response.status_code == 401


async def test_unknown_film_is_a_404(client: AsyncClient):
    assert (await client.get("/v1/films/ZZZZZZ")).status_code == 404
