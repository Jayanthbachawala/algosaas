from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    raw: dict[str, Any]


class BrokerAdapter(ABC):
    broker_name: str

    @abstractmethod
    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> OAuthToken:
        raise NotImplementedError

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> OAuthToken:
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, access_token: str, order_payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_positions(self, access_token: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_execution_confirmation(self, access_token: str, broker_order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def _post_form(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, data=payload)
        response.raise_for_status()
        return response.json()

    async def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _get(self, url: str, headers: dict[str, str], params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def _token_from_response(self, data: dict[str, Any]) -> OAuthToken:
        expires_in = int(data.get("expires_in", 3600))
        return OAuthToken(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            raw=data,
        )
