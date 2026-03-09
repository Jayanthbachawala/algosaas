from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="SubscriptionService", version="1.0.0")

PLAN_FEATURES = {
    "Basic": {"signals_per_day": 20, "paper_trading": True, "live_trading": False},
    "Pro": {"signals_per_day": 200, "paper_trading": True, "live_trading": True},
    "Premium": {"signals_per_day": 1000, "paper_trading": True, "live_trading": True},
}


class SubscriptionIn(BaseModel):
    user_id: UUID
    plan_code: str
    duration_days: int = 30


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/subscriptions")
async def create_subscription(payload: SubscriptionIn, db: AsyncSession = Depends(get_db_session)):
    if payload.plan_code not in PLAN_FEATURES:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    start_at = datetime.now(timezone.utc)
    end_at = start_at + timedelta(days=payload.duration_days)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO subscriptions(user_id, plan_code, status, start_at, end_at, features)
                VALUES (:user_id, :plan_code, 'active', :start_at, :end_at, CAST(:features AS jsonb))
                RETURNING id, user_id, plan_code, status, start_at, end_at, features
                """
            ),
            {
                "user_id": payload.user_id,
                "plan_code": payload.plan_code,
                "start_at": start_at,
                "end_at": end_at,
                "features": json.dumps(PLAN_FEATURES[payload.plan_code]),
            },
        )
    ).mappings().one()

    await redis_client.hset(f"subscription:{payload.user_id}", mapping={k: str(v) for k, v in dict(row).items()})
    return dict(row)


@app.get("/v1/subscriptions/{user_id}")
async def get_subscription(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    cached = await redis_client.hgetall(f"subscription:{user_id}")
    if cached:
        return {"source": "redis", "subscription": cached}

    row = (
        await db.execute(
            text(
                """
                SELECT id, user_id, plan_code, status, start_at, end_at, features
                FROM subscriptions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"source": "postgres", "subscription": dict(row)}


@app.get("/v1/subscriptions/{user_id}/entitlements")
async def entitlements(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                SELECT plan_code, features
                FROM subscriptions
                WHERE user_id = :user_id AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()

    if not row:
        return {"plan": "none", "features": {}, "execution_mode": ["PAPER"]}

    features = row["features"]
    execution_mode = ["PAPER", "LIVE"] if features.get("live_trading") else ["PAPER"]
    return {"plan": row["plan_code"], "features": features, "execution_mode": execution_mode}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "subscription-service"}
