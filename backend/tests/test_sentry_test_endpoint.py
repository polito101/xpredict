"""Sentry synthetic-trigger endpoint test — D-29 / PLT-08 (FastAPI surface)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_sentry_test_endpoint_raises_500(client: httpx.AsyncClient) -> None:
    """GET /_sentry-test propagates RuntimeError → FastAPI returns 500."""
    response = await client.get("/_sentry-test")
    assert response.status_code == 500
