from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="NotificationService", version="1.0.0")


class NotificationIn(BaseModel):
    user_id: UUID
    channel: str = "email"
    subject: str
    message: str


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/notifications/send")
async def send_notification(payload: NotificationIn):
    event = {
        "user_id": str(payload.user_id),
        "channel": payload.channel,
        "subject": payload.subject,
        "message": payload.message,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.lpush(f"notifications:{payload.user_id}", str(event))
    await redis_client.ltrim(f"notifications:{payload.user_id}", 0, 99)
    return {"queued": True, "event": event}


@app.get("/v1/notifications/{user_id}")
async def get_notifications(user_id: UUID):
    items = await redis_client.lrange(f"notifications:{user_id}", 0, 49)
    return {"user_id": str(user_id), "count": len(items), "notifications": items}


@app.post("/v1/notifications/{user_id}/digest")
async def risk_signal_digest(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    latest_risk = (
        await db.execute(
            text(
                """
                SELECT event_type, severity, payload, created_at
                FROM risk_events
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 5
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    latest_signals = (
        await db.execute(
            text(
                """
                SELECT symbol, strike, option_type, probability_score, generated_at
                FROM signals
                WHERE user_id = :user_id OR user_id IS NULL
                ORDER BY generated_at DESC
                LIMIT 5
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    digest = {
        "user_id": str(user_id),
        "risk_events": [dict(r) for r in latest_risk],
        "signals": [dict(r) for r in latest_signals],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.lpush(f"notifications:{user_id}", str(digest))
    await redis_client.ltrim(f"notifications:{user_id}", 0, 99)
    return digest


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service"}
