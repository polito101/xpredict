"""Public casino-demo catalog router (quick task 260611-u0q) under ``/api/v1``.

``GET /api/v1/casino/games`` -> ``CasinoCatalog`` ({status, games[]}). The read is
intentionally UNAUTHENTICATED — it mirrors ``public_catalog_router`` (no auth
dependency on the route), so the frontend Server Component can fetch it server-side
without forwarding a session.

IMPORTANT — this module deliberately OMITS the PEP 563 ``__future__`` annotations
import. With future annotations enabled, FastAPI sees the ``Depends()`` markers
inside ``Annotated[...]`` as bare strings and fails to resolve the dependency at
startup (422). Same constraint documented at the top of ``app/catalog/router.py``
and ``app/integrations/livebets/router.py``. Do NOT add the future-import here.

A ``get_slotslaunch_client()`` dependency returns the ``SlotsLaunchClient`` so tests
override it via ``app.dependency_overrides`` (mirrors ``get_livebets_client``) and
never hit the network; ``get_redis`` is the existing Redis dependency.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.integrations.slotslaunch.client import SlotsLaunchClient
from app.integrations.slotslaunch.schemas import CasinoCatalog
from app.integrations.slotslaunch.service import get_catalog

casino_router = APIRouter(prefix="/api/v1", tags=["casino"])


def get_slotslaunch_client() -> SlotsLaunchClient:
    """The SlotsLaunch client used by the route.

    Tests override this with a fake via ``app.dependency_overrides`` (mirrors
    ``get_livebets_client`` / ``get_market_source``) so they never hit the network.
    """
    return SlotsLaunchClient()


@casino_router.get("/casino/games", response_model=CasinoCatalog)
async def list_casino_games(
    redis: Annotated[Redis, Depends(get_redis)],
    client: Annotated[SlotsLaunchClient, Depends(get_slotslaunch_client)],
) -> CasinoCatalog:
    """Public demo-slots catalog — ``{status: active|inactive, games[]}``.

    Always HTTP 200: active with backend-composed iframe URLs when the SlotsLaunch
    subscription is live, ``{status:"inactive",games:[]}`` otherwise (subscription
    off, upstream failure, or token unset). Never 500s on an upstream problem
    (T-u0q-04). The catalog is Redis-cached server-side (T-u0q-03).
    """
    return await get_catalog(redis, client)


__all__ = ["casino_router", "get_slotslaunch_client"]
