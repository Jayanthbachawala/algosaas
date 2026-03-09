from uuid import UUID

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="PortfolioService", version="1.0.0")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.get("/v1/portfolio/{user_id}/summary")
async def portfolio_summary(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    positions = (
        await db.execute(
            text(
                """
                SELECT symbol, strike, option_type, net_qty, avg_price, ltp, unrealized_pnl, realized_pnl
                FROM positions
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    pnl_row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sum(unrealized_pnl),0) AS unrealized,
                       COALESCE(sum(realized_pnl),0) AS realized
                FROM positions
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one()

    cache_key = f"portfolio:summary:{user_id}"
    result = {
        "user_id": str(user_id),
        "positions": [dict(r) for r in positions],
        "unrealized_pnl": float(pnl_row["unrealized"]),
        "realized_pnl": float(pnl_row["realized"]),
        "net_pnl": float(pnl_row["unrealized"]) + float(pnl_row["realized"]),
    }
    await redis_client.hset(cache_key, mapping={k: str(v) for k, v in result.items() if k != "positions"})
    return result


@app.get("/v1/portfolio/{user_id}/exposure")
async def exposure(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sum(abs(net_qty * avg_price)),0) AS gross_exposure,
                       COALESCE(sum(CASE WHEN option_type='CE' THEN net_qty ELSE 0 END),0) AS ce_qty,
                       COALESCE(sum(CASE WHEN option_type='PE' THEN net_qty ELSE 0 END),0) AS pe_qty
                FROM positions
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one()
    return {"user_id": str(user_id), **{k: float(v) for k, v in row.items()}}


@app.get("/v1/portfolio/{user_id}/signals-context")
async def signals_context(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    signal = (
        await db.execute(
            text(
                """
                SELECT symbol, strike, option_type, entry_price, stop_loss, target_price, probability_score, generated_at
                FROM signals
                WHERE user_id = :user_id OR user_id IS NULL
                ORDER BY generated_at DESC
                LIMIT 10
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    recent_orders = (
        await db.execute(
            text(
                """
                SELECT broker_order_id, symbol, strike, option_type, side, quantity, status, mode, created_at
                FROM orders
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 10
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    return {
        "user_id": str(user_id),
        "latest_signals": [dict(r) for r in signal],
        "recent_orders": [dict(r) for r in recent_orders],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "portfolio-service"}
