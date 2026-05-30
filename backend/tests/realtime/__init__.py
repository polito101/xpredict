"""Realtime WebSocket fan-out integration tests (MKT-04).

These tests exercise the full producer → Redis pub/sub → FastAPI subscriber →
WS-client pipeline lifted from spike 003. They are marked ``integration`` and
run against the REAL docker-compose ``redis`` service — fakeredis cross-connection
pub/sub semantics are unreliable (09-RESEARCH Validation Architecture note).
"""
