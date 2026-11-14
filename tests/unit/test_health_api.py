"""Tests for the liveness and readiness probes.

The three dependency checks are patched out — this is about the endpoint's
contract (status codes and the reported checks), not about whether Postgres
is actually running.
"""

import pytest
from httpx import AsyncClient

from app.api import health

CHECKS = ("_check_postgres", "_check_redis", "_check_qdrant")


def _patch(monkeypatch: pytest.MonkeyPatch, name: str, error: Exception | None) -> None:
    """Make one dependency check succeed, or fail with `error`."""

    async def _check() -> None:
        if error is not None:
            raise error

    monkeypatch.setattr(health, name, _check)


@pytest.fixture
def all_up(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CHECKS:
        _patch(monkeypatch, name, None)


async def test_health_is_always_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_every_dependency_is_up(
    client: AsyncClient, all_up: None
) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"postgres": "ok", "redis": "ok", "qdrant": "ok"}


@pytest.mark.parametrize(
    ("failing", "dependency"),
    [
        ("_check_postgres", "postgres"),
        ("_check_redis", "redis"),
        ("_check_qdrant", "qdrant"),
    ],
)
async def test_ready_is_503_when_a_dependency_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, failing: str, dependency: str
) -> None:
    for name in CHECKS:
        _patch(monkeypatch, name, None)
    _patch(monkeypatch, failing, ConnectionError("boom"))

    response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"][dependency] == "error: ConnectionError"


async def test_ready_reports_the_other_checks_as_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in CHECKS:
        _patch(monkeypatch, name, None)
    _patch(monkeypatch, "_check_redis", ConnectionError("boom"))

    body = (await client.get("/ready")).json()

    assert body["checks"]["redis"].startswith("error:")
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["qdrant"] == "ok"


async def test_a_failure_does_not_leak_the_error_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in CHECKS:
        _patch(monkeypatch, name, None)
    _patch(monkeypatch, "_check_postgres", RuntimeError("password=hunter2 host=db"))

    body = (await client.get("/ready")).json()

    assert "hunter2" not in body["checks"]["postgres"]
    assert body["checks"]["postgres"] == "error: RuntimeError"


async def test_the_probes_are_documented(client: AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]

    assert "/health" in paths
    assert "/ready" in paths
