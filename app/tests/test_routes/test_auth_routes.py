from httpx import AsyncClient

from app.tests.factories import user_payload


async def test_signup_success(client: AsyncClient):
    payload = user_payload()
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["email"] == payload["email"]
    assert data["username"] == payload["username"]


async def test_signup_duplicate_email(client: AsyncClient):
    payload = user_payload()
    await client.post("/api/v1/auth/signup", json=payload)
    payload2 = user_payload(email=payload["email"])
    resp = await client.post("/api/v1/auth/signup", json=payload2)
    assert resp.status_code == 409


async def test_signup_weak_password(client: AsyncClient):
    payload = user_payload(password="abc")
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 422


async def test_login_success(client: AsyncClient):
    payload = user_payload()
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data


async def test_login_wrong_password(client: AsyncClient):
    payload = user_payload()
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": "WrongPass1",
        },
    )
    assert resp.status_code == 401


async def test_refresh_success(client: AsyncClient):
    payload = user_payload()
    await client.post("/api/v1/auth/signup", json=payload)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    refresh_token = login.json()["data"]["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]


async def test_refresh_with_access_token_rejected(client: AsyncClient):
    payload = user_payload()
    await client.post("/api/v1/auth/signup", json=payload)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    access_token = login.json()["data"]["access_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


async def test_logout_authenticated(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.post("/api/v1/auth/logout", headers=auth_headers)
    assert resp.status_code == 204


async def test_logout_unauthenticated(client: AsyncClient):
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 401


async def test_get_profile(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/v1/auth/profile", headers=auth_headers)
    assert resp.status_code == 200
    assert "email" in resp.json()["data"]


async def test_get_profile_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/profile")
    assert resp.status_code == 401


async def test_update_profile_name(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.patch(
        "/api/v1/auth/profile",
        headers=auth_headers,
        json={"full_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Updated Name"


async def test_update_profile_password(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.patch(
        "/api/v1/auth/profile",
        headers=auth_headers,
        json={"password": "NewPassword1"},
    )
    assert resp.status_code == 200
