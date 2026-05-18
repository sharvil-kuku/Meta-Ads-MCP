"""Unit tests for core/meta_client.py — all network calls mocked."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.meta_client import MetaClient, TransientMetaError


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, content=json.dumps(body).encode())


def _ok(body: dict) -> httpx.Response:
    return _make_response(200, body)


def _err(code: int, msg: str, http_status: int = 400) -> httpx.Response:
    return _make_response(
        http_status, {"error": {"code": code, "message": msg, "type": "GraphMethodException"}}
    )


# ── TransientMetaError detection ───────────────────────────────────────────────


class TestIsTransient:
    def setup_method(self):
        self.client = MetaClient()

    def test_transient_by_code(self):
        assert self.client._is_transient({"code": 4, "message": "rate limit"})

    def test_transient_by_message(self):
        assert self.client._is_transient({"code": 999, "message": "please reduce the rate"})

    def test_not_transient(self):
        assert not self.client._is_transient({"code": 100, "message": "Invalid parameter"})

    def test_transient_code_1(self):
        assert self.client._is_transient({"code": 1, "message": "unknown error"})


# ── _parse_response ────────────────────────────────────────────────────────────


class TestParseResponse:
    def setup_method(self):
        self.client = MetaClient()

    def test_success(self):
        resp = _ok({"id": "123", "name": "Test"})
        result = self.client._parse_response(resp)
        assert result == {"id": "123", "name": "Test"}

    def test_transient_error_raises_transient(self):
        resp = _err(4, "rate limit exceeded", 400)
        with pytest.raises(TransientMetaError):
            self.client._parse_response(resp)

    def test_non_transient_error_raises_exception(self):
        resp = _err(100, "Invalid parameter", 400)
        with pytest.raises(Exception) as exc:
            self.client._parse_response(resp)
        assert "Invalid parameter" in str(exc.value)

    def test_non_json_error(self):
        resp = httpx.Response(status_code=500, content=b"Internal Server Error")
        with pytest.raises(Exception) as exc:
            self.client._parse_response(resp)
        assert "HTTP 500" in str(exc.value)


# ── GET ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGet:
    async def test_get_returns_parsed_dict(self):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ok({"id": "me123", "name": "Test User"}))

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            result = await client.get("me", fields=["id", "name"])

        assert result["id"] == "me123"
        call_kwargs = mock_http.get.call_args
        assert "access_token" in call_kwargs.kwargs["params"]
        assert call_kwargs.kwargs["params"]["fields"] == "id,name"

    async def test_get_no_fields(self):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_ok({"data": []}))

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            result = await client.get("me/adaccounts")

        assert "data" in result
        params = mock_http.get.call_args.kwargs["params"]
        assert "fields" not in params


# ── Paginate ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPaginate:
    async def test_single_page(self):
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(
            return_value=_ok({"data": [{"id": "1"}, {"id": "2"}], "paging": {}})
        )

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            results = await client.paginate("me/adaccounts", {"fields": "id"})

        assert len(results) == 2
        assert results[0]["id"] == "1"

    async def test_two_pages(self):
        page1 = _ok({"data": [{"id": "1"}], "paging": {"next": "https://graph.facebook.com/page2"}})
        page2 = _ok({"data": [{"id": "2"}], "paging": {}})

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[page1, page2])

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            results = await client.paginate("me/adaccounts", {"fields": "id"})

        assert len(results) == 2
        assert mock_http.get.call_count == 2


# ── Write ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWrite:
    async def test_write_sends_params_as_query(self):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_ok({"success": True}))

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            result = await client.write("23851234567890", {"daily_budget": "200000"})

        assert result == {"success": True}
        call_kwargs = mock_http.post.call_args
        params = call_kwargs.kwargs["params"]
        assert params["daily_budget"] == "200000"
        assert "access_token" in params

    async def test_write_url_uses_object_path(self):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_ok({"success": True}))

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            await client.write("act_123/campaigns", {"status": "PAUSED"})

        url = mock_http.post.call_args.args[0]
        assert "act_123/campaigns" in url


# ── Batch ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPostBatch:
    async def test_batch_parses_body_strings(self):
        batch_response = [
            {"code": 200, "body": json.dumps({"data": [{"id": "1"}]})},
            {"code": 200, "body": json.dumps({"data": [{"id": "2"}]})},
        ]
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_ok(batch_response))

        client = MetaClient()
        with patch.object(client, "get_client", return_value=mock_http):
            results = await client.post_batch(
                [
                    {"method": "GET", "relative_url": "1/insights"},
                    {"method": "GET", "relative_url": "2/insights"},
                ]
            )

        assert len(results) == 2
        assert results[0]["body"]["data"][0]["id"] == "1"

    async def test_batch_chunking(self):
        single_page_result = [{"code": 200, "body": json.dumps({"id": str(i)})} for i in range(5)]
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=_ok(single_page_result))

        requests = [{"method": "GET", "relative_url": f"{i}/insights"} for i in range(30)]

        client = MetaClient()
        with (
            patch.object(client, "get_client", return_value=mock_http),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            results = await client.post_batch(requests)

        # 30 requests / 25 chunk_size = 2 POST calls
        assert mock_http.post.call_count == 2
        assert len(results) == 10  # 5 results × 2 chunks
