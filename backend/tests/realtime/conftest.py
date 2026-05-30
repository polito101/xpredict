"""Fixtures for the realtime WS fan-out integration tests (MKT-04).

The pipeline under test (producer → Redis pub/sub → FastAPI subscriber → WS
client) needs a REAL ASGI server bound to a socket so the ``websockets`` client
performs a genuine WebSocket handshake while the in-process ``redis_subscriber``
background task fans out published deltas. httpx's ASGITransport cannot drive a
long-lived WS + a concurrent lifespan subscriber the way a real uvicorn server
can, so we spin a uvicorn server on an ephemeral port for the duration of the
module (spike 003 ran the server on a real port for exactly this reason).

Redis is the docker-compose ``redis`` service (``settings.REDIS_URL``); fakeredis
cross-connection pub/sub is unreliable (09-RESEARCH Validation Architecture note),
so these tests are marked ``integration``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
import redis
import uvicorn
from fastapi import FastAPI


def _free_port() -> int:
    """Grab an unused TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _build_realtime_app() -> FastAPI:
    """Build a minimal FastAPI app that mounts ``realtime_router`` and starts the
    ``redis_subscriber`` background task in its lifespan — the production wiring
    from ``app/main.py``, isolated to the realtime surface for the test server.

    Imports are deferred to call time: in Task 1 (RED) ``app.realtime`` does not
    yet exist, so this raises ``ModuleNotFoundError`` and the tests fail RED — a
    genuine RED→GREEN signal until Tasks 2-3 land.
    """
    from app.core.config import get_settings
    from app.realtime.manager import manager
    from app.realtime.router import realtime_router
    from app.realtime.subscriber import redis_subscriber

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(redis_subscriber(manager, str(settings.REDIS_URL)))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(lifespan=lifespan)
    app.include_router(realtime_router)
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def ws_server() -> AsyncIterator[str]:
    """Run the realtime app on an ephemeral uvicorn port; yield the ``ws://`` base.

    The server's lifespan starts the ``redis_subscriber`` background task, so a
    publish to ``prices:{id}`` fans out to a connected client exactly as in prod.
    """
    app = _build_realtime_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())

    # Wait for uvicorn to flip ``started`` (its lifespan — incl. the subscriber —
    # has run by then) before handing the URL to the test.
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - server failed to come up
        raise RuntimeError("uvicorn test server failed to start")

    try:
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await serve_task


@pytest.fixture
def publish_delta() -> Callable[[str, dict], int]:
    """Return a sync publisher that pushes a JSON payload to ``prices:{market_id}``.

    Uses a short-lived sync ``redis`` client (the same shape the production
    publisher uses), matching the spike's cross-connection publish path.
    """
    from app.core.config import get_settings

    settings = get_settings()
    client = redis.from_url(str(settings.REDIS_URL))

    def _publish(market_id: str, payload: dict) -> int:
        return int(client.publish(f"prices:{market_id}", json.dumps(payload)))

    try:
        yield _publish
    finally:
        client.close()
