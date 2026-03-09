import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="RiskManagementService", version="1.0.0")
producer = KafkaProducerClient()


class RiskCheckIn(BaseModel):
    user_id: UUID
    symbol: str
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    max_position_size: int = 500
    max_open_trades: int = 10
    daily_loss_limit: float = -25000.0
    implied_volatility: float = 0.0


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/risk/check")
async def risk_check(payload: RiskCheckIn, db: AsyncSession = Depends(get_db_session)):
    reasons: list[str] = []

    open_trade_count = (
        await db.execute(
            text("SELECT count(*) FROM trades WHERE user_id = :user_id AND closed_at IS NULL"),
            {"user_id": payload.user_id},
        )
    ).scalar_one()

    day_pnl = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sum(pnl), 0)
                FROM trades
                WHERE user_id = :user_id
                  AND opened_at::date = CURRENT_DATE
                """
            ),
            {"user_id": payload.user_id},
        )
    ).scalar_one()

    notional = payload.quantity * payload.entry_price
    if payload.quantity > payload.max_position_size:
        reasons.append("max_position_size_exceeded")
    if open_trade_count >= payload.max_open_trades:
        reasons.append("max_open_trades_exceeded")
    if float(day_pnl) <= payload.daily_loss_limit:
        reasons.append("daily_loss_limit_exceeded")
    if payload.implied_volatility >= 45.0:
        reasons.append("volatility_protection_triggered")

    allowed = len(reasons) == 0
    result = {
        "allowed": allowed,
        "user_id": str(payload.user_id),
        "symbol": payload.symbol,
        "notional": round(notional, 2),
        "open_trade_count": int(open_trade_count),
        "day_pnl": float(day_pnl),
        "reasons": reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    await redis_client.hset(f"risk:last:{payload.user_id}", mapping={k: json.dumps(v) if isinstance(v, list) else str(v) for k, v in result.items()})

    if not allowed:
        await db.execute(
            text(
                """
                INSERT INTO risk_events(user_id, event_type, severity, payload)
                VALUES (:user_id, :event_type, :severity, CAST(:payload AS jsonb))
                """
            ),
            {
                "user_id": payload.user_id,
                "event_type": "pre_trade_blocked",
                "severity": "CRITICAL" if "daily_loss_limit_exceeded" in reasons else "HIGH",
                "payload": json.dumps(result),
            },
        )
        await producer.send(settings.risk_alert_topic, result)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "risk-management-service"}
