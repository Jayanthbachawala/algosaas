from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="AIModelService", version="1.0.0")
producer = KafkaProducerClient()


class TrainRequest(BaseModel):
    model_name: str
    model_type: str
    artifact_uri: str
    training_window_days: int = 180


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/models/train-request")
async def request_training(payload: TrainRequest, db: AsyncSession = Depends(get_db_session)):
    version = datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    row = (
        await db.execute(
            text(
                """
                INSERT INTO model_registry(model_name, model_type, version, artifact_uri, metrics, status)
                VALUES (:model_name, :model_type, :version, :artifact_uri, '{}'::jsonb, 'TRAINING')
                RETURNING id, model_name, model_type, version, status, created_at
                """
            ),
            {
                "model_name": payload.model_name,
                "model_type": payload.model_type,
                "version": version,
                "artifact_uri": payload.artifact_uri,
            },
        )
    ).mappings().one()

    event = {
        "model_id": str(row["id"]),
        "model_name": row["model_name"],
        "model_type": row["model_type"],
        "version": row["version"],
        "training_window_days": payload.training_window_days,
        "requested_at": row["created_at"].isoformat(),
    }
    await producer.send(settings.model_training_requested_topic, event)
    return event


@app.post("/v1/models/deploy/{model_id}")
async def deploy_model(model_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                UPDATE model_registry
                SET status = 'DEPLOYED', promoted_at = now()
                WHERE id = :model_id
                RETURNING id, model_name, version, model_type, artifact_uri, promoted_at
                """
            ),
            {"model_id": model_id},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Model not found")

    redis_key = f"model:active:{row['model_name']}"
    await redis_client.hset(
        redis_key,
        mapping={
            "model_id": str(row["id"]),
            "model_name": row["model_name"],
            "version": row["version"],
            "model_type": row["model_type"],
            "artifact_uri": row["artifact_uri"],
        },
    )

    event = {
        "model_id": str(row["id"]),
        "model_name": row["model_name"],
        "version": row["version"],
        "deployed_at": row["promoted_at"].isoformat(),
    }
    await producer.send(settings.model_deployed_topic, event)
    return event


@app.get("/v1/models/active/{model_name}")
async def active_model(model_name: str, db: AsyncSession = Depends(get_db_session)):
    redis_key = f"model:active:{model_name}"
    cached = await redis_client.hgetall(redis_key)
    if cached:
        return {"source": "redis", "model": cached}

    row = (
        await db.execute(
            text(
                """
                SELECT id, model_name, model_type, version, artifact_uri, promoted_at
                FROM model_registry
                WHERE model_name = :model_name AND status = 'DEPLOYED'
                ORDER BY promoted_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"model_name": model_name},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="No active model")
    return {"source": "postgres", "model": dict(row)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-model-service"}
