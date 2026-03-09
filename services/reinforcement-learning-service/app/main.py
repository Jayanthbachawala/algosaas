import asyncio
import json
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="ReinforcementLearningService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.execution_outcome_topic, "reinforcement-learning-service")
consumer_task: asyncio.Task | None = None


class ExperienceIn(BaseModel):
    symbol: str
    market_regime: str
    oi_structure: dict
    iv_level: float
    greeks: dict
    entry_price: float
    exit_price: float
    pnl: float


async def _store_experience(payload: ExperienceIn, db: AsyncSession) -> dict:
    reward = round(payload.pnl - max(0.0, payload.iv_level - 40) * 0.05, 4)
    label = payload.pnl > 0

    await db.execute(
        text(
            """
            INSERT INTO ai_training_dataset(
                ts, symbol, market_regime, oi_structure, iv_level, greeks,
                entry_price, exit_price, pnl, reward, feature_vector, label_profitable
            ) VALUES (
                :ts, :symbol, :market_regime, CAST(:oi_structure AS jsonb), :iv_level, CAST(:greeks AS jsonb),
                :entry_price, :exit_price, :pnl, :reward, CAST(:feature_vector AS jsonb), :label_profitable
            )
            """
        ),
        {
            "ts": datetime.now(timezone.utc),
            "symbol": payload.symbol,
            "market_regime": payload.market_regime,
            "oi_structure": json.dumps(payload.oi_structure),
            "iv_level": payload.iv_level,
            "greeks": json.dumps(payload.greeks),
            "entry_price": payload.entry_price,
            "exit_price": payload.exit_price,
            "pnl": payload.pnl,
            "reward": reward,
            "feature_vector": json.dumps(
                {
                    "market_regime": payload.market_regime,
                    "iv_level": payload.iv_level,
                    "entry_price": payload.entry_price,
                    "exit_price": payload.exit_price,
                }
            ),
            "label_profitable": label,
        },
    )

    update = {
        "symbol": payload.symbol,
        "reward": reward,
        "pnl": payload.pnl,
        "label_profitable": label,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.hset(f"rl:last:{payload.symbol}", mapping={k: str(v) for k, v in update.items()})
    return update


async def _consume_outcomes() -> None:
    async for event in consumer.messages():
        if "symbol" not in event:
            continue
        payload = ExperienceIn(
            symbol=event["symbol"],
            market_regime=event.get("market_regime", "unknown"),
            oi_structure=event.get("oi_structure", {}),
            iv_level=float(event.get("iv_level", 0.0)),
            greeks=event.get("greeks", {}),
            entry_price=float(event.get("entry_price", 0.0)),
            exit_price=float(event.get("exit_price", 0.0)),
            pnl=float(event.get("pnl", 0.0)),
        )
        async for db in get_db_session():
            update = await _store_experience(payload, db)
            if update["reward"] < -1000:
                await producer.send(
                    settings.model_training_requested_topic,
                    {
                        "reason": "negative_reward_drift",
                        "symbol": payload.symbol,
                        "reward": update["reward"],
                    },
                )


@app.on_event("startup")
async def startup_event() -> None:
    global consumer_task
    await producer.start()
    await consumer.start()
    consumer_task = asyncio.create_task(_consume_outcomes())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if consumer_task:
        consumer_task.cancel()
    await consumer.stop()
    await producer.stop()
    await redis_client.close()


@app.post("/v1/rl/experience")
async def add_experience(payload: ExperienceIn, db: AsyncSession = Depends(get_db_session)):
    update = await _store_experience(payload, db)
    await producer.send(settings.execution_outcome_topic, update)
    return update


@app.get("/health")
async def health():
    return {"status": "ok", "service": "reinforcement-learning-service"}
