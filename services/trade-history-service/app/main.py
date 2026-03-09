from uuid import UUID

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="TradeHistoryService", version="1.0.0")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.get("/v1/trades/{user_id}")
async def trades(user_id: UUID, limit: int = 100, db: AsyncSession = Depends(get_db_session)):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, order_id, symbol, strike, option_type, side, entry_price, exit_price, quantity, pnl, opened_at, closed_at
                FROM trades
                WHERE user_id = :user_id
                ORDER BY opened_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
    ).mappings().all()
    return {"user_id": str(user_id), "count": len(rows), "trades": [dict(r) for r in rows]}


@app.get("/v1/trades/{user_id}/orders")
async def orders(user_id: UUID, limit: int = 100, db: AsyncSession = Depends(get_db_session)):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, broker_order_id, symbol, strike, option_type, side, quantity, order_type, status, mode, created_at
                FROM orders
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
    ).mappings().all()
    return {"user_id": str(user_id), "count": len(rows), "orders": [dict(r) for r in rows]}


@app.get("/v1/trades/{user_id}/performance")
async def performance(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS total_trades,
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),0) AS winning_trades,
                       COALESCE(SUM(pnl),0) AS net_pnl
                FROM trades
                WHERE user_id = :user_id AND closed_at IS NOT NULL
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one()

    total = int(row["total_trades"])
    wins = int(row["winning_trades"])
    win_rate = round((wins / total) * 100, 2) if total else 0.0
    result = {
        "user_id": str(user_id),
        "total_trades": total,
        "winning_trades": wins,
        "win_rate": win_rate,
        "net_pnl": float(row["net_pnl"]),
    }
    await redis_client.hset(f"trades:performance:{user_id}", mapping={k: str(v) for k, v in result.items()})
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "trade-history-service"}
