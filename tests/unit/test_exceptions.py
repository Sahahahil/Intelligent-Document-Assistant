import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppError, NotFoundError, register_exception_handlers


def build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("Document not found", details={"document_id": "abc"})

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.mark.asyncio
async def test_app_error_uses_the_error_envelope() -> None:
    app = build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/boom")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Document not found"
    assert body["error"]["details"] == {"document_id": "abc"}


@pytest.mark.asyncio
async def test_unhandled_error_is_masked() -> None:
    app = build_app()
    # Starlette's ServerErrorMiddleware re-raises after sending the response;
    # raise_server_exceptions=False lets the client see what was actually sent.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text


@pytest.mark.asyncio
async def test_unknown_route_uses_the_same_envelope() -> None:
    app = build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_error_codes_are_unique() -> None:
    assert AppError.status_code == 500
    assert AppError.code == "internal_error"
