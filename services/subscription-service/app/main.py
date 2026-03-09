import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.entitlements import resolve_feature_access
from services.common.redis_client import redis_client

app = FastAPI(title="SubscriptionService", version="2.0.0")

from services.common.saas_logic import PLAN_FEATURES

PLAN_MATRIX = PLAN_FEATURES


class PlanIn(BaseModel):
    name: str
    price: float
    billing_cycle: str = "monthly"


class SubscribeIn(BaseModel):
    user_id: UUID
    plan_name: str
    duration_days: int = 30


class OverrideIn(BaseModel):
    user_id: UUID
    feature_key: str
    enabled: bool


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


async def _ensure_seed_data(db: AsyncSession):
    # seed plans
    for name, price in (("Basic", 999), ("Pro", 2499), ("Premium", 4999)):
        await db.execute(
            text(
                """
                INSERT INTO plans(name, price, billing_cycle)
                VALUES (:name, :price, 'monthly')
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": name, "price": price},
        )

    # seed features
    for feature_key in PLAN_MATRIX["Premium"].keys():
        await db.execute(
            text(
                """
                INSERT INTO features(feature_key, description)
                VALUES (:feature_key, :description)
                ON CONFLICT (feature_key) DO NOTHING
                """
            ),
            {"feature_key": feature_key, "description": feature_key.replace("_", " ")},
        )

    # seed plan_features
    for plan, features in PLAN_MATRIX.items():
        plan_id = (
            await db.execute(text("SELECT id FROM plans WHERE name=:name"), {"name": plan})
        ).scalar_one()
        for key, enabled in features.items():
            feature_id = (
                await db.execute(text("SELECT id FROM features WHERE feature_key=:k"), {"k": key})
            ).scalar_one()
            await db.execute(
                text(
                    """
                    INSERT INTO plan_features(plan_id, feature_id, enabled)
                    VALUES (:plan_id, :feature_id, :enabled)
                    ON CONFLICT (plan_id, feature_id)
                    DO UPDATE SET enabled = EXCLUDED.enabled
                    """
                ),
                {"plan_id": plan_id, "feature_id": feature_id, "enabled": enabled},
            )


@app.post("/v1/plans/seed")
async def seed(db: AsyncSession = Depends(get_db_session)):
    await _ensure_seed_data(db)
    return {"seeded": True}


@app.get("/plans")
@app.get("/v1/plans")
async def plans(db: AsyncSession = Depends(get_db_session)):
    await _ensure_seed_data(db)
    rows = (await db.execute(text("SELECT id, name, price, billing_cycle FROM plans ORDER BY price"))).mappings().all()
    return {"plans": [dict(r) for r in rows]}


@app.post("/subscribe")
@app.post("/v1/subscriptions")
async def subscribe(payload: SubscribeIn, db: AsyncSession = Depends(get_db_session)):
    await _ensure_seed_data(db)
    plan = (
        await db.execute(text("SELECT id, name FROM plans WHERE name=:name"), {"name": payload.plan_name})
    ).mappings().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    start = datetime.now(timezone.utc)
    end = start + timedelta(days=payload.duration_days)

    sub = (
        await db.execute(
            text(
                """
                INSERT INTO subscriptions(user_id, plan_id, plan_code, status, start_at, end_at, start_date, end_date, features)
                VALUES (:user_id, :plan_id, :plan_code, 'active', :start, :end, :start, :end, CAST(:features as jsonb))
                RETURNING id, user_id, plan_id, plan_code, status, start_date, end_date
                """
            ),
            {
                "user_id": payload.user_id,
                "plan_id": plan["id"],
                "plan_code": plan["name"],
                "start": start,
                "end": end,
                "features": json.dumps(PLAN_MATRIX[plan["name"]]),
            },
        )
    ).mappings().one()
    await redis_client.hset(f"subscription:{payload.user_id}", mapping={k: str(v) for k, v in dict(sub).items()})
    return dict(sub)


@app.get("/v1/subscriptions/{user_id}/entitlements")
async def entitlements(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    await _ensure_seed_data(db)
    data = {}
    for key in PLAN_MATRIX["Premium"].keys():
        data[key] = await resolve_feature_access(db, str(user_id), key)
    return {"user_id": str(user_id), "features": data}


@app.post("/v1/subscriptions/override")
async def feature_override(payload: OverrideIn, db: AsyncSession = Depends(get_db_session)):
    feature_id = (
        await db.execute(text("SELECT id FROM features WHERE feature_key=:key"), {"key": payload.feature_key})
    ).scalar_one_or_none()
    if not feature_id:
        raise HTTPException(status_code=404, detail="Feature not found")
    await db.execute(
        text(
            """
            INSERT INTO user_feature_overrides(user_id, feature_id, enabled)
            VALUES (:user_id, :feature_id, :enabled)
            ON CONFLICT (user_id, feature_id)
            DO UPDATE SET enabled = EXCLUDED.enabled
            """
        ),
        payload.model_dump(mode="json") | {"feature_id": feature_id},
    )
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "subscription-service"}
