import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="NotificationService", version="2.0.0")


class NotificationIn(BaseModel):
    user_id: UUID
    notification_type: str = "new_signal_alert"
    channel: str = "email"
    subject: str
    message: str
    telegram_webhook: str | None = None


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/notifications/send")
async def send_notification(payload: NotificationIn):
    event = {
        "user_id": str(payload.user_id),
        "notification_type": payload.notification_type,
        "channel": payload.channel,
        "subject": payload.subject,
        "message": payload.message,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.lpush(f"notifications:{payload.user_id}", json.dumps(event))
    await redis_client.ltrim(f"notifications:{payload.user_id}", 0, 199)
    return {"queued": True, "event": event}


@app.get("/v1/notifications/user/{user_id}")
@app.get("/v1/notifications/{user_id}")
async def get_notifications(user_id: UUID):
    items = await redis_client.lrange(f"notifications:{user_id}", 0, 99)
    return {"user_id": str(user_id), "count": len(items), "notifications": [json.loads(i) for i in items]}


@app.post("/v1/notifications/{user_id}/digest")
async def risk_signal_digest(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    latest_risk = (
        await db.execute(
            text("SELECT event_type, severity, payload, created_at FROM risk_events WHERE user_id=:u ORDER BY created_at DESC LIMIT 5"),
            {"u": user_id},
        )
    ).mappings().all()
    latest_signals = (
        await db.execute(
            text("SELECT symbol, strike, option_type, probability_score, generated_at FROM signals WHERE user_id=:u OR user_id IS NULL ORDER BY generated_at DESC LIMIT 5"),
            {"u": user_id},
        )
    ).mappings().all()
    digest = {
        "user_id": str(user_id),
        "notification_type": "risk_limit_reached",
        "risk_events": [dict(r) for r in latest_risk],
        "signals": [dict(r) for r in latest_signals],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.lpush(f"notifications:{user_id}", json.dumps(digest))
    await redis_client.ltrim(f"notifications:{user_id}", 0, 199)
    return digest


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service"}
