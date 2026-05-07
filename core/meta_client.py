import json
import asyncio
from typing import Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
import structlog
from config import settings
from constants import TRANSIENT_META_ERROR_CODES, TRANSIENT_META_MESSAGES

log = structlog.get_logger()


class TransientMetaError(Exception):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class MetaClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.base_url = f"https://graph.facebook.com/{settings.meta_api_version}"

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _is_transient(self, error: dict) -> bool:
        code = error.get("code")
        message = error.get("message", "").lower()
        if code in TRANSIENT_META_ERROR_CODES:
            return True
        for pattern in TRANSIENT_META_MESSAGES:
            if pattern in message:
                return True
        return False

    def _parse_response(self, resp: httpx.Response) -> dict:
        if resp.status_code != 200:
            try:
                error = resp.json()
                if "error" in error:
                    err = error["error"]
                    if self._is_transient(err):
                        raise TransientMetaError(err.get("message", ""), err.get("code"))
                    raise Exception(f"{err.get('type')}: {err.get('message')}")
            except json.JSONDecodeError:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(
            initial=2, max=30, jitter=0.5
        ),
        retry=retry_if_exception_type(TransientMetaError),
        reraise=True,
    )
    async def get(
        self, path: str, fields: Optional[list[str]] = None
    ) -> dict:
        client = await self.get_client()
        params = {"access_token": settings.meta_access_token}
        if fields:
            params["fields"] = ",".join(fields)

        url = f"{self.base_url}/{path}"
        log.info("meta_api_call", method="GET", path=path, attempt=1)
        try:
            resp = await client.get(url, params=params)
        except TransientMetaError:
            raise
        except Exception as e:
            raise TransientMetaError(str(e))

        return self._parse_response(resp)

    async def post(
        self, path: str, data: Optional[dict] = None
    ) -> dict:
        client = await self.get_client()
        params = {"access_token": settings.meta_access_token}
        url = f"{self.base_url}/{path}"

        log.info("meta_api_call", method="POST", path=path)
        try:
            resp = await client.post(url, params=params, json=data)
        except Exception as e:
            raise TransientMetaError(str(e))

        return self._parse_response(resp)

    async def paginate(self, path: str, params: dict) -> list[dict]:
        results = []
        paging_params = {**params, "access_token": settings.meta_access_token}
        url = f"{self.base_url}/{path}"

        while url:
            client = await self.get_client()
            log.info("meta_api_paginate", url=url)
            resp = await client.get(url, params=paging_params)
            data = self._parse_response(resp)

            data_list = data.get("data", [])
            results.extend(data_list)

            paging = data.get("paging", {})
            next_url = paging.get("next")
            if next_url:
                url = next_url
                paging_params = None
            else:
                url = None

        return results

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=0.5),
        retry=retry_if_exception_type(TransientMetaError),
        reraise=True,
    )
    async def write(self, path: str, fields: dict) -> dict:
        """Update a Meta object (budget change, status change).
        Sends POST with params as query string — Meta Graph API write pattern."""
        client = await self.get_client()
        params = {"access_token": settings.meta_access_token, **fields}
        url = f"{self.base_url}/{path}"
        log.info("meta_api_write", path=path, fields=list(fields.keys()))
        try:
            resp = await client.post(url, params=params)
        except TransientMetaError:
            raise
        except Exception as e:
            raise TransientMetaError(str(e))
        return self._parse_response(resp)

    async def post_batch(self, batch: list[dict]) -> list[dict]:
        chunk_size = settings.batch_size
        all_results = []

        for i in range(0, len(batch), chunk_size):
            chunk = batch[i : i + chunk_size]
            batch_json = json.dumps(
                [{"method": item.get("method"), "relative_url": item.get("relative_url")} for item in chunk]
            )

            client = await self.get_client()
            params = {
                "access_token": settings.meta_access_token,
                "batch": batch_json,
            }
            url = f"{self.base_url}/"

            log.info("meta_api_batch", size=len(chunk), chunk=i // chunk_size)
            resp = await client.post(url, params=params)
            data = self._parse_response(resp)

            for idx, item in enumerate(data):
                body = item.get("body", "")
                if isinstance(body, str):
                    try:
                        item["body"] = json.loads(body)
                    except json.JSONDecodeError:
                        pass
                all_results.append(item)

            if i + chunk_size < len(batch):
                await asyncio.sleep(settings.batch_sleep_ms / 1000)

        return all_results


meta_client = MetaClient()