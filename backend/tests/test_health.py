"""Health endpoint tests — the one piece of real Phase 1 behavior."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "XPredict"
    assert "version" in body


async def test_health_ready_reports_checks(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    # Readiness must never raise; it reports per-dependency status.
    assert "database" in body["checks"]
    assert body["status"] in {"ok", "degraded"}
