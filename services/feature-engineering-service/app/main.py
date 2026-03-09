import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.config import settings
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="FeatureEngineeringService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.market_tick_topic, "feature-engineering-service")
consumer_task: asyncio.Task | None = None


class FeaturePayload(BaseModel):
    symbol: str
    ltp: float
    oi: float = 0.0
    volume: float = 0.0
    iv: float = 0.0
    pcr: float = 1.0
    vwap: float | None = None


def _build_features(payload: FeaturePayload, previous_ltp: float | None) -> dict:
    momentum = 0.0 if not previous_ltp else (payload.ltp - previous_ltp) / max(previous_ltp, 1e-6)
    oi_change_pct = payload.oi / 100000.0
    volume_spike = payload.volume / 100000.0
    vwap = payload.vwap or payload.ltp
    vwap_deviation = (payload.ltp - vwap) / max(vwap, 1e-6)

    return {
        "symbol": payload.symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "oi_change": round(oi_change_pct, 6),
        "put_call_ratio": payload.pcr,
        "implied_volatility": payload.iv,
        "price_momentum": round(momentum, 6),
        "volume_spike": round(volume_spike, 6),
        "vwap_deviation": round(vwap_deviation, 6),
        "delta": 0.5,
        "gamma": 0.1,
        "theta": -0.05,
        "vega": 0.2,
    }


async def _consume_market_ticks() -> None:
    async for message in consumer.messages():
        symbol = message.get("symbol")
        if not symbol:
            continue

        ltp = float(message.get("ltp", 0.0))
        previous_key = f"fe:previous_ltp:{symbol}"
        previous_ltp_raw = await redis_client.get(previous_key)
        previous_ltp = float(previous_ltp_raw) if previous_ltp_raw else None

        engineered = _build_features(
            FeaturePayload(
                symbol=symbol,
                ltp=ltp,
                oi=float(message.get("oi", 0.0) or 0.0),
                volume=float(message.get("volume", 0.0) or 0.0),
            ),
            previous_ltp,
        )
        await redis_client.hset(f"features:{symbol}", mapping={k: str(v) for k, v in engineered.items()})
        await redis_client.set(previous_key, ltp)
        await producer.send(settings.features_topic, engineered)


@app.on_event("startup")
async def startup_event() -> None:
    global consumer_task
    await producer.start()
    await consumer.start()
    consumer_task = asyncio.create_task(_consume_market_ticks())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if consumer_task:
        consumer_task.cancel()
    await consumer.stop()
    await producer.stop()
    await redis_client.close()


@app.post("/v1/features/build")
async def build_features(payload: FeaturePayload):
    previous_ltp_raw = await redis_client.get(f"fe:previous_ltp:{payload.symbol}")
    previous_ltp = float(previous_ltp_raw) if previous_ltp_raw else None
    engineered = _build_features(payload, previous_ltp)

    await redis_client.set(f"fe:previous_ltp:{payload.symbol}", payload.ltp)
    await redis_client.hset(f"features:{payload.symbol}", mapping={k: str(v) for k, v in engineered.items()})
    await producer.send(settings.features_topic, engineered)
    return engineered


@app.get("/v1/features/{symbol}")
async def latest_features(symbol: str):
    values = await redis_client.hgetall(f"features:{symbol}")
    return {"symbol": symbol, "features": values}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "feature-engineering-service"}
