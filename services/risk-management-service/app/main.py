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

app = FastAPI(title="RiskManagementService", version="2.0.0")
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
    bid_ask_spread: float = 0.0
    max_spread: float = 0.02
    max_capital_exposure: float = 500000.0


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


    global_kill = await redis_client.get("killswitch:global")
    if global_kill == "1":
        result = {
            "allowed": False,
            "user_id": str(payload.user_id),
            "symbol": payload.symbol,
            "reasons": ["global_trading_disabled"],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        await producer.send(settings.risk_alert_topic, result)
        return result

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

    exposure = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sum(abs(net_qty * avg_price)),0)
                FROM positions
                WHERE user_id = :user_id
                """
            ),
            {"user_id": payload.user_id},
        )
    ).scalar_one()

    notional = payload.quantity * payload.entry_price
    projected_exposure = float(exposure) + notional

    if payload.quantity > payload.max_position_size:
        reasons.append("max_position_size_exceeded")
    if open_trade_count >= payload.max_open_trades:
        reasons.append("max_open_trades_exceeded")
    if float(day_pnl) <= payload.daily_loss_limit:
        reasons.append("daily_loss_limit_exceeded")
    if payload.implied_volatility >= 45.0:
        reasons.append("volatility_risk_triggered")
    if payload.bid_ask_spread > payload.max_spread:
        reasons.append("liquidity_threshold_breached")
    if projected_exposure > payload.max_capital_exposure:
        reasons.append("max_exposure_exceeded")

    allowed = len(reasons) == 0
    result = {
        "allowed": allowed,
        "user_id": str(payload.user_id),
        "symbol": payload.symbol,
        "notional": round(notional, 2),
        "open_trade_count": int(open_trade_count),
        "day_pnl": float(day_pnl),
        "projected_exposure": round(projected_exposure, 2),
        "reasons": reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    await redis_client.hset(
        f"risk:last:{payload.user_id}",
        mapping={k: json.dumps(v) if isinstance(v, list) else str(v) for k, v in result.items()},
    )

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
