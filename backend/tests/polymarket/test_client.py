"""Tests for GammaClient — retry behavior and batch call verification.

Uses unittest.mock to mock httpx.AsyncClient without hitting the real
Gamma API. Proves MKT-05 rate-limit compliance (single batch call, not
per-market) and tenacity retry on transient errors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.integrations.polymarket.client import GammaClient

pytestmark = [pytest.mark.unit]


def _make_mock_response(
    json_data: list | dict | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
    return resp


class TestGammaClientFetchTopMarkets:
    """Tests for fetch_top_markets method."""

    @pytest.mark.asyncio
    async def test_single_batch_call(self) -> None:
        """MKT-05: exactly 1 GET request for top-25, not 25 per-market calls."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        sample_data = [{"id": str(i), "question": f"Q{i}"} for i in range(25)]
        mock_client.get = AsyncMock(return_value=_make_mock_response(sample_data))

        gamma = GammaClient()
        gamma._client = mock_client

        result = await gamma.fetch_top_markets(25)
        assert len(result) == 25
        # Exactly 1 GET call — not 25.
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self) -> None:
        """Retry succeeds after transient NetworkError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        success_resp = _make_mock_response([{"id": "1", "question": "Q"}])
        mock_client.get = AsyncMock(
            side_effect=[httpx.NetworkError("conn reset"), success_resp],
        )

        gamma = GammaClient()
        gamma._client = mock_client

        result = await gamma.fetch_top_markets(1)
        assert len(result) == 1
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self) -> None:
        """Retry succeeds after transient TimeoutException."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        success_resp = _make_mock_response([{"id": "1", "question": "Q"}])
        mock_client.get = AsyncMock(
            side_effect=[
                httpx.TimeoutException("read timeout"),
                success_resp,
            ],
        )

        gamma = GammaClient()
        gamma._client = mock_client

        result = await gamma.fetch_top_markets(1)
        assert len(result) == 1
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_3_attempts(self) -> None:
        """Raises NetworkError after exhausting 3 retry attempts."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(
            side_effect=httpx.NetworkError("persistent failure"),
        )

        gamma = GammaClient()
        gamma._client = mock_client

        with pytest.raises(httpx.NetworkError):
            await gamma.fetch_top_markets(1)
        assert mock_client.get.call_count == 3


class TestGammaClientFetchEvents:
    """Tests for fetch_events method (CAT-01 sync via GET /events)."""

    @pytest.mark.asyncio
    async def test_fetch_events_single_get_to_events(self) -> None:
        """CAT-01: exactly 1 GET to the /events path, returns the JSON list."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        sample_data = [{"id": str(i), "title": f"E{i}"} for i in range(3)]
        mock_client.get = AsyncMock(return_value=_make_mock_response(sample_data))

        gamma = GammaClient()
        gamma._client = mock_client

        result = await gamma.fetch_events(tag_id="2", limit=10)
        assert len(result) == 3
        assert mock_client.get.call_count == 1
        path_arg = mock_client.get.call_args.args[0]
        assert path_arg == "/events"

    @pytest.mark.asyncio
    async def test_fetch_events_params(self) -> None:
        """CAT-01: the single /events GET carries the curation params."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(
            return_value=_make_mock_response([{"id": "1", "title": "E1"}]),
        )

        gamma = GammaClient()
        gamma._client = mock_client

        await gamma.fetch_events(tag_id="21", limit=10)

        assert mock_client.get.call_count == 1
        assert mock_client.get.call_args.args[0] == "/events"
        params = mock_client.get.call_args.kwargs["params"]
        assert params["tag_id"] == "21"
        assert params["order"] == "volume24hr"
        assert params["ascending"] == "false"
        assert params["active"] == "true"
        assert params["closed"] == "false"

    @pytest.mark.asyncio
    async def test_fetch_events_caps_limit(self) -> None:
        """CAT-05: limit=999 is hard-capped — the sent limit param is '500'."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_make_mock_response([]))

        gamma = GammaClient()
        gamma._client = mock_client

        await gamma.fetch_events(tag_id="2", limit=999)

        params = mock_client.get.call_args.kwargs["params"]
        assert params["limit"] == "500"
