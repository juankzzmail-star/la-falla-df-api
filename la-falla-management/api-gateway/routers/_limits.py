"""Lightweight, fail-open abuse guards for public (unauthenticated) endpoints.

Used by the `edt_onboarding` router, which is intentionally public but calls paid
LLMs — so it needs basic cost/abuse protection without an API key.

Design notes:
- BEST-EFFORT only. The rate limiter is in-process (per uvicorn worker), so with N
  workers the effective limit is ~N x the configured rate. For hard guarantees use a
  shared store (e.g. Redis). This is a first-pass guard, not a security boundary.
- FAIL OPEN. Any unexpected internal error allows the request through, so these guards
  can never take down a legitimate endpoint. Only the explicit 413/429 paths block.

Env overrides:
- PUBLIC_MAX_BODY_BYTES (default 524288 = 512 KB)
- PUBLIC_RATE_PER_MIN  (default 20 requests per IP per minute)
"""
import os
import time
from collections import defaultdict, deque

from fastapi import Request, HTTPException

_MAX_BODY_BYTES = int(os.environ.get("PUBLIC_MAX_BODY_BYTES", str(512 * 1024)))
_RATE_MAX = int(os.environ.get("PUBLIC_RATE_PER_MIN", "20"))
_RATE_WINDOW = 60.0

# in-memory per-IP hit log: { ip -> deque[monotonic_timestamp] }
_hits: "defaultdict[str, deque]" = defaultdict(deque)


def body_size_cap(request: Request) -> None:
    """Reject requests whose declared body is larger than the cap (HTTP 413)."""
    try:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > _MAX_BODY_BYTES:
            raise HTTPException(413, f"Request body too large (max {_MAX_BODY_BYTES} bytes)")
    except HTTPException:
        raise
    except Exception:
        return  # fail open


def rate_limit(request: Request) -> None:
    """Per-IP sliding-window rate limit (HTTP 429 when exceeded)."""
    try:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        dq = _hits[ip]
        while dq and (now - dq[0]) > _RATE_WINDOW:
            dq.popleft()
        if len(dq) >= _RATE_MAX:
            raise HTTPException(429, "Too many requests — slow down")
        dq.append(now)
    except HTTPException:
        raise
    except Exception:
        return  # fail open
