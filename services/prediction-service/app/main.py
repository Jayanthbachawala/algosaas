from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="PredictionService", version="1.0.0")
producer = KafkaProducerClient()


class PredictionInput(BaseModel):
    symbol: str
    strike: float
    option_type: str
    oi_change: float
    put_call_ratio: float
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    price_momentum: float
    volume_spike: float
    vwap_deviation: float


class PredictionOutput(BaseModel):
    probability_profitable: float = Field(ge=0.0, le=1.0)
    expected_move: float
    confidence_interval: tuple[float, float]
    model_version: str


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


def _score(payload: PredictionInput) -> float:
    weighted = 0.0
    weighted += 0.22 * min(max(payload.oi_change, -1), 1)
    weighted += 0.12 * (1 - min(abs(payload.put_call_ratio - 1.0), 1.0))
    weighted += 0.14 * min(payload.implied_volatility / 80.0, 1.0)
    weighted += 0.08 * min(abs(payload.delta), 1.0)
    weighted += 0.06 * min(abs(payload.gamma), 1.0)
    weighted += 0.12 * min(abs(payload.price_momentum), 1.0)
    weighted += 0.14 * min(payload.volume_spike / 3.0, 1.0)
    weighted += 0.12 * (1 - min(abs(payload.vwap_deviation), 1.0))
    return max(0.0, min(1.0, round(0.5 + weighted / 2, 4)))


async def _active_model_version(db: AsyncSession) -> str:
    row = (
        await db.execute(
            text(
                """
                SELECT model_name, version
                FROM model_registry
                WHERE status='DEPLOYED'
                ORDER BY promoted_at DESC NULLS LAST
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    if not row:
        return "baseline-v1"
    return f"{row['model_name']}:{row['version']}"


@app.post("/v1/predictions/infer", response_model=PredictionOutput)
async def infer(payload: PredictionInput, db: AsyncSession = Depends(get_db_session)):
    probability = _score(payload)
    expected_move = round(payload.price_momentum * payload.strike * 0.03, 2)
    spread = round(max(0.02, (1 - probability) * 0.2), 4)
    ci = (max(0.0, round(probability - spread, 4)), min(1.0, round(probability + spread, 4)))
    model_version = await _active_model_version(db)

    result = PredictionOutput(
        probability_profitable=probability,
        expected_move=expected_move,
        confidence_interval=ci,
        model_version=model_version,
    )

    event = {
        "symbol": payload.symbol,
        "strike": payload.strike,
        "option_type": payload.option_type,
        "probability_profitable": result.probability_profitable,
        "expected_move": result.expected_move,
        "confidence_interval": list(result.confidence_interval),
        "model_version": result.model_version,
    }
    await redis_client.hset(
        f"prediction:{payload.symbol}:{payload.strike}:{payload.option_type}",
        mapping={k: str(v) for k, v in event.items()},
    )
    await producer.send(settings.prediction_topic, event)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "prediction-service"}
