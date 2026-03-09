import base64
import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

from .adapters.indian_brokers import ADAPTER_REGISTRY

app = FastAPI(title="BrokerGatewayService", version="2.0.0")
producer = KafkaProducerClient()

SUPPORTED_BROKERS = {"Zerodha", "Upstox", "Dhan", "Shoonya"}


class BrokerOrderIn(BaseModel):
    user_id: UUID
    broker_name: str
    symbol: str
    strike: float
    option_type: str
    side: str
    quantity: int = Field(gt=0)
    order_type: str = "MARKET"
    price: float | None = None


class OAuthConnectIn(BaseModel):
    user_id: UUID
    broker_name: str
    client_code: str


class TokenRefreshIn(BaseModel):
    user_id: UUID
    broker_name: str
    client_code: str


def _adapter_key(broker_name: str) -> str:
    return broker_name.strip().lower()


def _encrypt_token(token: str) -> bytes:
    return base64.b64encode(token.encode("utf-8"))


def _decrypt_token(token_bytes: bytes | None) -> str:
    if not token_bytes:
        return ""
    return base64.b64decode(token_bytes).decode("utf-8")


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/broker/oauth/connect")
async def oauth_connect(payload: OAuthConnectIn):
    broker = payload.broker_name
    if broker not in SUPPORTED_BROKERS:
        raise HTTPException(status_code=400, detail="Broker not supported")

    adapter = ADAPTER_REGISTRY[_adapter_key(broker)]
    state = f"{payload.user_id}:{payload.client_code}:{secrets.token_hex(8)}"
    await redis_client.setex(f"broker:oauth:state:{state}", 600, json.dumps(payload.model_dump(mode="json")))
    return {
        "authorization_url": adapter.authorization_url(state),
        "state": state,
        "broker": broker,
    }


@app.get("/v1/broker/oauth/{broker}/callback")
async def oauth_callback(
    broker: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    state_data = await redis_client.get(f"broker:oauth:state:{state}")
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired oauth state")

    payload = json.loads(state_data)
    user_id = payload["user_id"]
    client_code = payload["client_code"]

    adapter = ADAPTER_REGISTRY.get(_adapter_key(broker))
    if not adapter:
        raise HTTPException(status_code=400, detail="Unsupported broker callback")

    token = await adapter.exchange_code_for_token(code)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO broker_connections(
                    user_id, broker_name, client_code, encrypted_access_token, encrypted_refresh_token, token_expires_at, status
                ) VALUES (
                    :user_id, :broker_name, :client_code, :access, :refresh, :expires_at, 'active'
                )
                ON CONFLICT (user_id, broker_name, client_code)
                DO UPDATE SET
                  encrypted_access_token = EXCLUDED.encrypted_access_token,
                  encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                  token_expires_at = EXCLUDED.token_expires_at,
                  status = 'active'
                RETURNING id, user_id, broker_name, client_code, token_expires_at
                """
            ),
            {
                "user_id": user_id,
                "broker_name": broker.capitalize() if broker != "upstox" else "Upstox",
                "client_code": client_code,
                "access": _encrypt_token(token.access_token),
                "refresh": _encrypt_token(token.refresh_token or ""),
                "expires_at": token.expires_at,
            },
        )
    ).mappings().one()

    event = {
        "type": "OAUTH_CONNECTED",
        "connection_id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "broker_name": row["broker_name"],
        "client_code": row["client_code"],
        "token_expires_at": row["token_expires_at"].isoformat(),
    }
    await producer.send(settings.order_lifecycle_topic, event)
    return event


@app.post("/v1/broker/auth/refresh")
async def refresh_token(payload: TokenRefreshIn, db: AsyncSession = Depends(get_db_session)):
    adapter = ADAPTER_REGISTRY.get(_adapter_key(payload.broker_name))
    if not adapter:
        raise HTTPException(status_code=400, detail="Broker not supported")

    row = (
        await db.execute(
            text(
                """
                SELECT id, encrypted_refresh_token
                FROM broker_connections
                WHERE user_id = :user_id AND broker_name = :broker_name AND client_code = :client_code
                LIMIT 1
                """
            ),
            payload.model_dump(mode="json"),
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Broker connection not found")

    refresh = _decrypt_token(row["encrypted_refresh_token"])
    if not refresh:
        raise HTTPException(status_code=400, detail="Refresh token unavailable")

    token = await adapter.refresh_access_token(refresh)

    saved = (
        await db.execute(
            text(
                """
                UPDATE broker_connections
                SET encrypted_access_token = :access,
                    encrypted_refresh_token = :refresh,
                    token_expires_at = :expires_at,
                    status = 'active'
                WHERE id = :id
                RETURNING id, user_id, broker_name, client_code, token_expires_at
                """
            ),
            {
                "id": row["id"],
                "access": _encrypt_token(token.access_token),
                "refresh": _encrypt_token(token.refresh_token or refresh),
                "expires_at": token.expires_at,
            },
        )
    ).mappings().one()

    event = {
        "type": "TOKEN_REFRESHED",
        "connection_id": str(saved["id"]),
        "user_id": str(saved["user_id"]),
        "broker_name": saved["broker_name"],
        "client_code": saved["client_code"],
        "token_expires_at": saved["token_expires_at"].isoformat(),
    }
    await producer.send(settings.order_lifecycle_topic, event)
    return event


@app.post("/v1/broker/orders")
async def place_live_order(payload: BrokerOrderIn, db: AsyncSession = Depends(get_db_session)):
    if payload.broker_name not in SUPPORTED_BROKERS:
        raise HTTPException(status_code=400, detail="Broker not supported")

    adapter = ADAPTER_REGISTRY[_adapter_key(payload.broker_name)]
    conn = (
        await db.execute(
            text(
                """
                SELECT id, encrypted_access_token, token_expires_at, status
                FROM broker_connections
                WHERE user_id = :user_id AND broker_name = :broker_name
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": payload.user_id, "broker_name": payload.broker_name},
        )
    ).mappings().first()
    if not conn or conn["status"] != "active":
        raise HTTPException(status_code=403, detail="Active broker connection required")

    access_token = _decrypt_token(conn["encrypted_access_token"])
    broker_order = await adapter.place_order(access_token, payload.model_dump(mode="json"))
    broker_order_id = broker_order.get("broker_order_id") or f"{payload.broker_name[:3].upper()}-{int(datetime.now(timezone.utc).timestamp())}"

    order_id = (
        await db.execute(
            text(
                """
                INSERT INTO orders(user_id, mode, broker_order_id, symbol, strike, option_type, side, quantity, order_type, limit_price, status)
                VALUES (:user_id, 'LIVE', :broker_order_id, :symbol, :strike, :option_type, :side, :quantity, :order_type, :limit_price, :status)
                RETURNING id
                """
            ),
            {
                "user_id": payload.user_id,
                "broker_order_id": broker_order_id,
                "symbol": payload.symbol,
                "strike": payload.strike,
                "option_type": payload.option_type,
                "side": payload.side,
                "quantity": payload.quantity,
                "order_type": payload.order_type,
                "limit_price": payload.price,
                "status": broker_order.get("status", "ACCEPTED"),
            },
        )
    ).scalar_one()

    event = {
        "type": "ORDER_PLACED",
        "order_id": str(order_id),
        "broker_order_id": broker_order_id,
        "broker_name": payload.broker_name,
        "user_id": str(payload.user_id),
        "symbol": payload.symbol,
        "status": broker_order.get("status", "ACCEPTED"),
        "mode": "LIVE",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.hset(f"broker:last-order:{payload.user_id}", mapping={k: str(v) for k, v in event.items()})
    await producer.send(settings.order_lifecycle_topic, event)
    return event


@app.get("/v1/broker/positions/{user_id}/{broker_name}")
async def positions(user_id: UUID, broker_name: str, db: AsyncSession = Depends(get_db_session)):
    adapter = ADAPTER_REGISTRY.get(_adapter_key(broker_name))
    if not adapter:
        raise HTTPException(status_code=400, detail="Broker not supported")

    conn = (
        await db.execute(
            text(
                """
                SELECT encrypted_access_token
                FROM broker_connections
                WHERE user_id = :user_id AND broker_name = :broker_name
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id, "broker_name": broker_name},
        )
    ).mappings().first()
    if not conn:
        raise HTTPException(status_code=404, detail="Broker connection not found")

    positions_data = await adapter.fetch_positions(_decrypt_token(conn["encrypted_access_token"]))
    return {"user_id": str(user_id), "broker_name": broker_name, **positions_data}


@app.get("/v1/broker/orders/{broker_name}/{broker_order_id}/confirmation")
async def execution_confirmation(broker_name: str, broker_order_id: str, user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    adapter = ADAPTER_REGISTRY.get(_adapter_key(broker_name))
    if not adapter:
        raise HTTPException(status_code=400, detail="Broker not supported")

    conn = (
        await db.execute(
            text(
                """
                SELECT encrypted_access_token
                FROM broker_connections
                WHERE user_id = :user_id AND broker_name = :broker_name
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id, "broker_name": broker_name},
        )
    ).mappings().first()
    if not conn:
        raise HTTPException(status_code=404, detail="Broker connection not found")

    confirmation = await adapter.fetch_execution_confirmation(
        _decrypt_token(conn["encrypted_access_token"]),
        broker_order_id,
    )

    await db.execute(
        text(
            """
            UPDATE orders
            SET status = :status, updated_at = now()
            WHERE broker_order_id = :broker_order_id
            """
        ),
        {
            "status": confirmation.get("exchange_status", "CONFIRMED"),
            "broker_order_id": broker_order_id,
        },
    )

    event = {
        "type": "EXECUTION_CONFIRMED",
        "broker_name": broker_name,
        "broker_order_id": broker_order_id,
        "exchange_status": confirmation.get("exchange_status"),
        "filled_quantity": confirmation.get("filled_quantity", 0),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await producer.send(settings.execution_outcome_topic, event)
    return {**confirmation, "event": event}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "broker-gateway-service"}
