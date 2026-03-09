import random
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="PaperTradingService", version="1.0.0")
producer = KafkaProducerClient()


class PaperOrderIn(BaseModel):
    user_id: UUID
    symbol: str
    strike: float
    option_type: str
    side: str
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


def _simulate_fill(entry_price: float, quantity: int) -> dict:
    slippage = random.uniform(-0.005, 0.01)
    latency_ms = random.randint(20, 450)
    fill_ratio = random.uniform(0.6, 1.0)
    filled_qty = max(1, int(quantity * fill_ratio))
    fill_price = round(entry_price * (1 + slippage), 2)
    return {
        "fill_price": fill_price,
        "filled_qty": filled_qty,
        "latency_ms": latency_ms,
        "slippage": round(slippage, 6),
        "partial_fill": filled_qty < quantity,
    }


@app.post("/v1/paper/orders")
async def place_paper_order(payload: PaperOrderIn, db: AsyncSession = Depends(get_db_session)):
    fill = _simulate_fill(payload.entry_price, payload.quantity)

    order_row = (
        await db.execute(
            text(
                """
                INSERT INTO orders(user_id, mode, symbol, strike, option_type, side, quantity, order_type, limit_price, status)
                VALUES (:user_id, 'PAPER', :symbol, :strike, :option_type, :side, :quantity, 'MARKET', :limit_price, 'FILLED')
                RETURNING id
                """
            ),
            {
                "user_id": payload.user_id,
                "symbol": payload.symbol,
                "strike": payload.strike,
                "option_type": payload.option_type,
                "side": payload.side,
                "quantity": fill["filled_qty"],
                "limit_price": fill["fill_price"],
            },
        )
    ).scalar_one()

    trade_row = (
        await db.execute(
            text(
                """
                INSERT INTO trades(user_id, order_id, symbol, strike, option_type, side, entry_price, quantity, opened_at)
                VALUES (:user_id, :order_id, :symbol, :strike, :option_type, :side, :entry_price, :quantity, :opened_at)
                RETURNING id
                """
            ),
            {
                "user_id": payload.user_id,
                "order_id": order_row,
                "symbol": payload.symbol,
                "strike": payload.strike,
                "option_type": payload.option_type,
                "side": payload.side,
                "entry_price": fill["fill_price"],
                "quantity": fill["filled_qty"],
                "opened_at": datetime.now(timezone.utc),
            },
        )
    ).scalar_one()

    event = {
        "order_id": str(order_row),
        "trade_id": str(trade_row),
        "user_id": str(payload.user_id),
        "symbol": payload.symbol,
        "entry_price": fill["fill_price"],
        "fill_qty": fill["filled_qty"],
        "latency_ms": fill["latency_ms"],
        "slippage": fill["slippage"],
        "partial_fill": fill["partial_fill"],
        "mode": "PAPER",
    }
    await producer.send(settings.order_lifecycle_topic, event)
    await redis_client.hset(f"paper:last:{payload.symbol}", mapping={k: str(v) for k, v in event.items()})
    return event


@app.post("/v1/paper/auto-run")
async def auto_paper_trade(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
    events = []
    for symbol in symbols:
        tick = await redis_client.hgetall(f"tick:{symbol}")
        ltp = float(tick.get("ltp", 100.0)) if tick else 100.0
        payload = PaperOrderIn(
            user_id=user_id,
            symbol=symbol,
            strike=round(ltp),
            option_type="CE",
            side="BUY",
            quantity=50,
            entry_price=ltp,
        )
        events.append(await place_paper_order(payload, db))
    return {"count": len(events), "events": events}


@app.post("/v1/paper/close/{trade_id}")
async def close_trade(trade_id: UUID, exit_price: float, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                SELECT id, symbol, entry_price, quantity, side
                FROM trades
                WHERE id = :trade_id
                """
            ),
            {"trade_id": trade_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Trade not found")

    pnl = (exit_price - float(row["entry_price"])) * int(row["quantity"])
    if row["side"] == "SELL":
        pnl = -pnl

    await db.execute(
        text(
            """
            UPDATE trades
            SET exit_price = :exit_price, pnl = :pnl, closed_at = now()
            WHERE id = :trade_id
            """
        ),
        {"trade_id": trade_id, "exit_price": exit_price, "pnl": pnl},
    )

    outcome = {
        "trade_id": str(trade_id),
        "symbol": row["symbol"],
        "entry_price": float(row["entry_price"]),
        "exit_price": exit_price,
        "pnl": round(pnl, 2),
        "market_regime": "paper",
        "oi_structure": {},
        "iv_level": 0,
        "greeks": {},
    }
    await producer.send(settings.execution_outcome_topic, outcome)
    return outcome


@app.get("/health")
async def health():
    return {"status": "ok", "service": "paper-trading-service"}
