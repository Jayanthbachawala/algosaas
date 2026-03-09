import json
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="AdminService", version="1.0.0")


class UserStatusIn(BaseModel):
    user_id: UUID
    status: str


class ChangePlanIn(BaseModel):
    user_id: UUID
    plan_name: str


class TrialIn(BaseModel):
    user_id: UUID
    days: int = 7


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


async def _audit(db: AsyncSession, action_type: str, payload: dict):
    await db.execute(
        text("INSERT INTO admin_actions(action_type, payload) VALUES (:action_type, CAST(:payload as jsonb))"),
        {"action_type": action_type, "payload": json.dumps(payload)},
    )


@app.get("/v1/admin/dashboard")
async def admin_dashboard(db: AsyncSession = Depends(get_db_session)):
    users = (await db.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
    active_users = (await db.execute(text("SELECT COUNT(*) FROM users WHERE status='active'"))).scalar_one()
    subscriptions = (await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE status='active'"))).scalar_one()
    signals = (await db.execute(text("SELECT COUNT(*) FROM signals WHERE generated_at::date=CURRENT_DATE"))).scalar_one()
    trades = (await db.execute(text("SELECT COUNT(*) FROM trades WHERE opened_at::date=CURRENT_DATE"))).scalar_one()
    revenue = (await db.execute(text("SELECT COALESCE(SUM(amount_paise),0) FROM billing_invoices WHERE status='paid'"))).scalar_one()

    return {
        "users_total": int(users),
        "active_users": int(active_users),
        "active_subscriptions": int(subscriptions),
        "signals_generated_today": int(signals),
        "trades_executed_today": int(trades),
        "total_revenue_paise": int(revenue),
    }


@app.get("/v1/admin/users")
async def users(db: AsyncSession = Depends(get_db_session)):
    rows = (
        await db.execute(text("SELECT id, email, status, created_at FROM users ORDER BY created_at DESC LIMIT 500"))
    ).mappings().all()
    return {"users": [dict(r) for r in rows]}


@app.post("/v1/admin/users/status")
async def update_user_status(payload: UserStatusIn, db: AsyncSession = Depends(get_db_session)):
    await db.execute(text("UPDATE users SET status=:status, updated_at=now() WHERE id=:user_id"), payload.model_dump(mode="json"))
    await _audit(db, "user_status_update", payload.model_dump(mode="json"))
    return {"ok": True}


@app.post("/v1/admin/users/change-plan")
async def change_plan(payload: ChangePlanIn, db: AsyncSession = Depends(get_db_session)):
    plan = (await db.execute(text("SELECT id FROM plans WHERE name=:n"), {"n": payload.plan_name})).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await db.execute(
        text(
            """
            UPDATE subscriptions
            SET plan_id=:plan_id, plan_code=:plan_name, updated_at=now()
            WHERE user_id=:user_id AND status='active'
            """
        ),
        {"plan_id": plan, "plan_name": payload.plan_name, "user_id": str(payload.user_id)},
    )
    await _audit(db, "change_plan", payload.model_dump(mode="json"))
    return {"ok": True}


@app.post("/v1/admin/users/grant-trial")
async def grant_trial(payload: TrialIn, db: AsyncSession = Depends(get_db_session)):
    await db.execute(
        text(
            """
            UPDATE subscriptions
            SET end_date = COALESCE(end_date, now()) + make_interval(days => :days)
            WHERE user_id = :user_id AND status='active'
            """
        ),
        {"user_id": str(payload.user_id), "days": payload.days},
    )
    await _audit(db, "grant_trial", payload.model_dump(mode="json"))
    return {"ok": True}


@app.post("/admin/disable-trading")
async def disable_trading(db: AsyncSession = Depends(get_db_session)):
    await redis_client.set("killswitch:global", "1")
    await _audit(db, "disable_trading", {"ts": datetime.now(timezone.utc).isoformat()})
    return {"trading_enabled": False}


@app.post("/admin/enable-trading")
async def enable_trading(db: AsyncSession = Depends(get_db_session)):
    await redis_client.set("killswitch:global", "0")
    await _audit(db, "enable_trading", {"ts": datetime.now(timezone.utc).isoformat()})
    return {"trading_enabled": True}


@app.get("/v1/admin/monitoring")
async def monitoring(db: AsyncSession = Depends(get_db_session)):
    redis_info = await redis_client.info("memory")
    sessions = len(await redis_client.keys("auth:access:*"))
    metrics = (
        await db.execute(
            text(
                """
                SELECT metric_key, metric_value, ts
                FROM monitoring_metrics
                ORDER BY ts DESC
                LIMIT 200
                """
            )
        )
    ).mappings().all()
    return {
        "redis_memory_used": redis_info.get("used_memory_human"),
        "active_sessions": sessions,
        "metrics": [dict(r) for r in metrics],
    }


@app.get("/v1/admin/signals/performance")
async def signal_performance(db: AsyncSession = Depends(get_db_session)):
    total = (await db.execute(text("SELECT COUNT(*) FROM trades WHERE closed_at IS NOT NULL"))).scalar_one()
    wins = (await db.execute(text("SELECT COUNT(*) FROM trades WHERE closed_at IS NOT NULL AND pnl > 0"))).scalar_one()
    net = (await db.execute(text("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE closed_at IS NOT NULL"))).scalar_one()
    win_rate = (wins / total * 100) if total else 0
    return {"total_closed_trades": int(total), "win_rate": round(win_rate, 2), "net_pnl": float(net)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "admin-service"}
