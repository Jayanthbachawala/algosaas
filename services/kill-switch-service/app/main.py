import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="KillSwitchService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.risk_alert_topic, "kill-switch-service")
consumer_task: asyncio.Task | None = None


class KillSwitchRequest(BaseModel):
    user_id: UUID | None = None
    trigger_reason: str
    scope: str = "GLOBAL"


async def _activate(payload: KillSwitchRequest, db: AsyncSession, activated: bool = True) -> dict:
    scope_key = "global" if payload.user_id is None else str(payload.user_id)
    await redis_client.set(f"killswitch:{scope_key}", "1" if activated else "0")

    await db.execute(
        text(
            """
            INSERT INTO killswitch_events(user_id, trigger_reason, scope, activated)
            VALUES (:user_id, :trigger_reason, :scope, :activated)
            """
        ),
        {
            "user_id": payload.user_id,
            "trigger_reason": payload.trigger_reason,
            "scope": payload.scope,
            "activated": activated,
        },
    )

    result = {
        "user_id": str(payload.user_id) if payload.user_id else None,
        "scope": payload.scope,
        "trigger_reason": payload.trigger_reason,
        "activated": activated,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await producer.send(settings.kill_switch_topic, result)
    return result


async def _consume_risk_alerts() -> None:
    async for event in consumer.messages():
        reasons = event.get("reasons", [])
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except json.JSONDecodeError:
                reasons = [reasons]
        if "daily_loss_limit_exceeded" in reasons or "volatility_protection_triggered" in reasons:
            req = KillSwitchRequest(
                user_id=UUID(event["user_id"]) if event.get("user_id") else None,
                trigger_reason="risk_alert_trigger",
                scope="USER" if event.get("user_id") else "GLOBAL",
            )
            async for db in get_db_session():
                await _activate(req, db, activated=True)


@app.on_event("startup")
async def startup_event() -> None:
    global consumer_task
    await producer.start()
    await consumer.start()
    consumer_task = asyncio.create_task(_consume_risk_alerts())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if consumer_task:
        consumer_task.cancel()
    await consumer.stop()
    await producer.stop()
    await redis_client.close()


@app.post("/v1/killswitch/activate")
async def activate_killswitch(payload: KillSwitchRequest, db: AsyncSession = Depends(get_db_session)):
    return await _activate(payload, db, activated=True)


@app.post("/v1/killswitch/deactivate")
async def deactivate_killswitch(payload: KillSwitchRequest, db: AsyncSession = Depends(get_db_session)):
    return await _activate(payload, db, activated=False)


@app.get("/v1/killswitch/status")
async def killswitch_status(user_id: UUID | None = None):
    scope_key = "global" if user_id is None else str(user_id)
    status = await redis_client.get(f"killswitch:{scope_key}")
    return {"scope": scope_key, "activated": status == "1"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kill-switch-service"}
