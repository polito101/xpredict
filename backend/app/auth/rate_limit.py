"""slowapi Limiter — per-IP AND per-email keys for auth endpoints (D-14, AUTH-08).

Uses Redis DB /1 as the storage backend (DB /0 is the general app cache —
isolating the slowapi keyspace avoids accidental key collisions). The
``SLOWAPI_STORAGE_URI`` env var, if set, overrides the Redis URI — tests
use ``memory://`` to avoid an external Redis dependency.

# Per-IP + Per-Email composition (D-14, AUTH-08)

slowapi evaluates each ``@limiter.limit(...)`` ``key_func`` BEFORE the
route body runs, so reading the email field from a JSON / form body
isn't possible at decoration time. Stacking ``@limiter.limit(...,
key_func=get_remote_address)`` AND a ``key_func=email_key_func`` that
reads ``request.state.rate_limit_email_key`` doesn't work because the
state attribute is only set inside the body (too late).

# Composition pattern used by ``router.py``

- The decorator stack applies the per-IP limit via
  ``@limiter.limit("5/minute", key_func=get_remote_address)``.
- Inside the route body (where the email is available from the parsed
  pydantic body or OAuth2 form), the route calls
  ``check_email_limit(request, email)`` which hits a per-email bucket
  in slowapi's underlying storage. On exceed it raises
  ``RateLimitExceeded`` (the global exception handler in main.py turns
  it into a generic 429).

This composition still gives Per-IP AND Per-Email simultaneous
protection (the two checks must BOTH pass) while remaining compatible
with slowapi's decorator model.
"""

from __future__ import annotations

import os

from fastapi import Request
from limits import parse as parse_limit
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()


def _build_storage_uri() -> str:
    """Compose the slowapi storage_uri targeting Redis DB /1.

    settings.REDIS_URL might already include a /N suffix (e.g.
    ``redis://localhost:6379/0``); we strip the trailing DB number and
    append /1 unconditionally so slowapi never collides with the app's
    general cache keyspace.

    ``SLOWAPI_STORAGE_URI`` env override — tests use ``memory://``.
    """
    override = os.environ.get("SLOWAPI_STORAGE_URI")
    if override:
        return override
    base = str(_settings.REDIS_URL).rstrip("/")
    parts = base.rsplit("/", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
    return f"{base}/1"


limiter = Limiter(
    key_func=get_remote_address,                # per-IP default
    storage_uri=_build_storage_uri(),
    default_limits=[],
    headers_enabled=True,
)


def check_email_limit(
    request: Request,
    email: str,
    limit_str: str = "5/minute",
) -> None:
    """Per-email rate-limit check, invoked from inside the route body.

    Uses slowapi's underlying ``limits`` storage directly so we share the
    same backend (Redis DB /1 in prod, ``memory://`` in tests) as the
    per-IP decorator stack.

    Raises ``RateLimitExceeded`` if exceeded. The global handler in
    ``main.py`` turns this into a 429 with a generic message (T-02-08 /
    T-02-10 — message must NOT reveal whether the email exists).
    """
    request.state.rate_limit_email_key = f"email:{email.strip().lower()}"
    limit_item = parse_limit(limit_str)
    # Bucket key includes the URL path so /auth/login and /auth/register
    # don't share a single email counter. Matches slowapi's own keying.
    key = f"email:{email.strip().lower()}:{request.url.path}"
    # ``limiter._limiter`` is the underlying ``limits`` strategy.
    if not limiter._limiter.hit(limit_item, key):
        raise RateLimitExceeded(_LimitProxy(limit_item))  # type: ignore[arg-type]


class _LimitProxy:
    """Minimal stand-in matching the .limit attr that slowapi's handler reads."""

    def __init__(self, limit_item: object) -> None:
        self.limit = limit_item
        self.error_message: str | None = None


__all__ = [
    "check_email_limit",
    "get_remote_address",
    "limiter",
]
