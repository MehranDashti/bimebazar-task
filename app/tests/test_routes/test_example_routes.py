from httpx import AsyncClient

from app.tests.factories import example_payload


async def test_create_example(client: AsyncClient, auth_headers: dict[str, str]):
    payload = example_payload()
    resp = await client.post("/api/v1/examples", headers=auth_headers, json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == payload["name"]
    assert "id" in data


async def test_create_example_duplicate(client: AsyncClient, auth_headers: dict[str, str]):
    payload = example_payload()
    await client.post("/api/v1/examples", headers=auth_headers, json=payload)
    resp = await client.post("/api/v1/examples", headers=auth_headers, json=payload)
    assert resp.status_code == 409


async def test_list_examples(client: AsyncClient, auth_headers: dict[str, str]):
    for _ in range(3):
        await client.post("/api/v1/examples", headers=auth_headers, json=example_payload())
    resp = await client.get("/api/v1/examples", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["meta"]["total"] == 3


async def test_list_examples_filter_by_name(client: AsyncClient, auth_headers: dict[str, str]):
    await client.post(
        "/api/v1/examples", headers=auth_headers, json=example_payload(name="apple-one")
    )
    await client.post(
        "/api/v1/examples", headers=auth_headers, json=example_payload(name="banana-two")
    )
    resp = await client.get("/api/v1/examples?name=apple", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["meta"]["total"] == 1


async def test_get_example(client: AsyncClient, auth_headers: dict[str, str]):
    create_resp = await client.post(
        "/api/v1/examples", headers=auth_headers, json=example_payload()
    )
    example_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/examples/{example_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == example_id


async def test_get_example_not_found(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/v1/examples/9999", headers=auth_headers)
    assert resp.status_code == 404


async def test_update_example(client: AsyncClient, auth_headers: dict[str, str]):
    create_resp = await client.post(
        "/api/v1/examples", headers=auth_headers, json=example_payload()
    )
    example_id = create_resp.json()["data"]["id"]
    resp = await client.patch(
        f"/api/v1/examples/{example_id}",
        headers=auth_headers,
        json={"name": "updated-name"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "updated-name"


async def test_delete_example(client: AsyncClient, auth_headers: dict[str, str]):
    create_resp = await client.post(
        "/api/v1/examples", headers=auth_headers, json=example_payload()
    )
    example_id = create_resp.json()["data"]["id"]
    resp = await client.delete(f"/api/v1/examples/{example_id}", headers=auth_headers)
    assert resp.status_code == 204


async def test_routes_require_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/examples")
    assert resp.status_code == 401
    resp = await client.post("/api/v1/examples", json=example_payload())
    assert resp.status_code == 401
