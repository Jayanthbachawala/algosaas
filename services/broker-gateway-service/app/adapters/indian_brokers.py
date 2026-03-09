from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .base import BrokerAdapter, OAuthToken
from ..core.config import broker_settings


class OAuthBrokerAdapter(BrokerAdapter):
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str
    token_url: str
    orders_url: str
    positions_url: str
    execution_url: str | None = None

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }
        )
        return f"{self.auth_url}?{query}"

    async def exchange_code_for_token(self, code: str) -> OAuthToken:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }
        data = await self._post_form(self.token_url, payload)
        return self._token_from_response(data)

    async def refresh_access_token(self, refresh_token: str) -> OAuthToken:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        data = await self._post_form(self.token_url, payload)
        return self._token_from_response(data)

    async def place_order(self, access_token: str, order_payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._post_json(
            self.orders_url,
            order_payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        broker_order_id = data.get("order_id") or data.get("data", {}).get("order_id") or data.get("id")
        return {"broker_order_id": broker_order_id, "raw": data, "status": data.get("status", "ACCEPTED")}

    async def fetch_positions(self, access_token: str) -> dict[str, Any]:
        data = await self._get(self.positions_url, headers={"Authorization": f"Bearer {access_token}"})
        return {"positions": data.get("data", data), "raw": data}

    async def fetch_execution_confirmation(self, access_token: str, broker_order_id: str) -> dict[str, Any]:
        execution_url = self.execution_url or f"{self.orders_url}/{broker_order_id}"
        data = await self._get(
            execution_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"order_id": broker_order_id},
        )
        return {
            "broker_order_id": broker_order_id,
            "exchange_status": data.get("status") or data.get("data", {}).get("status", "UNKNOWN"),
            "filled_quantity": data.get("filled_quantity") or data.get("data", {}).get("filled_quantity", 0),
            "raw": data,
        }


class ZerodhaAdapter(OAuthBrokerAdapter):
    broker_name = "Zerodha"
    client_id = broker_settings.zerodha_client_id
    client_secret = broker_settings.zerodha_client_secret
    redirect_uri = broker_settings.zerodha_redirect_uri
    auth_url = broker_settings.zerodha_auth_url
    token_url = broker_settings.zerodha_token_url
    orders_url = broker_settings.zerodha_orders_url
    positions_url = broker_settings.zerodha_positions_url


class UpstoxAdapter(OAuthBrokerAdapter):
    broker_name = "Upstox"
    client_id = broker_settings.upstox_client_id
    client_secret = broker_settings.upstox_client_secret
    redirect_uri = broker_settings.upstox_redirect_uri
    auth_url = broker_settings.upstox_auth_url
    token_url = broker_settings.upstox_token_url
    orders_url = broker_settings.upstox_orders_url
    positions_url = broker_settings.upstox_positions_url


class DhanAdapter(OAuthBrokerAdapter):
    broker_name = "Dhan"
    client_id = broker_settings.dhan_client_id
    client_secret = broker_settings.dhan_client_secret
    redirect_uri = broker_settings.dhan_redirect_uri
    auth_url = broker_settings.dhan_auth_url
    token_url = broker_settings.dhan_token_url
    orders_url = broker_settings.dhan_orders_url
    positions_url = broker_settings.dhan_positions_url


class ShoonyaAdapter(OAuthBrokerAdapter):
    broker_name = "Shoonya"
    client_id = broker_settings.shoonya_client_id
    client_secret = broker_settings.shoonya_client_secret
    redirect_uri = broker_settings.shoonya_redirect_uri
    auth_url = broker_settings.shoonya_auth_url
    token_url = broker_settings.shoonya_token_url
    orders_url = broker_settings.shoonya_orders_url
    positions_url = broker_settings.shoonya_positions_url


ADAPTER_REGISTRY = {
    "zerodha": ZerodhaAdapter(),
    "upstox": UpstoxAdapter(),
    "dhan": DhanAdapter(),
    "shoonya": ShoonyaAdapter(),
}
