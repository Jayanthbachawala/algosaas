import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.config import settings
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="VolatilitySurfaceService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.features_enriched_topic, "volatility-surface-service")
consumer_task: asyncio.Task | None = None


class VolSurfaceInput(BaseModel):
    symbol: str
    strike: float
    expiry_days: int = 7
    implied_volatility: float
    iv_change: float
    volatility_skew: float
    volatility_smile: float
    volatility_term_structure: float


def build_surface_signal(payload: VolSurfaceInput) -> dict:
    vol_surface_signal = max(
        0.0,
        min(
            1.0,
            0.35 * min(payload.implied_volatility / 60, 1)
            + 0.20 * min(abs(payload.iv_change), 1)
            + 0.20 * min(abs(payload.volatility_skew), 1)
            + 0.15 * min(abs(payload.volatility_smile), 1)
            + 0.10 * min(abs(payload.volatility_term_structure), 1),
        ),
    )
    regime = "high_volatility" if vol_surface_signal >= 0.65 else "low_volatility"
    return {
        "symbol": payload.symbol,
        "strike": payload.strike,
        "expiry_days": payload.expiry_days,
        "vol_surface_signal": round(vol_surface_signal, 6),
        "volatility_regime": regime,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _consume():
    async for m in consumer.messages():
        out = build_surface_signal(
            VolSurfaceInput(
                symbol=m.get("symbol", "UNKNOWN"),
                strike=float(m.get("strike", 0) or 0),
                implied_volatility=float(m.get("implied_volatility", 0) or 0),
                iv_change=float(m.get("iv_change", 0) or 0),
                volatility_skew=float(m.get("volatility_skew", 0) or 0),
                volatility_smile=float(m.get("volatility_smile", 0) or 0),
                volatility_term_structure=float(m.get("volatility_term_structure", 0) or 0),
            )
        )
        await redis_client.hset(f"volsurface:{out['symbol']}", mapping={k: str(v) for k, v in out.items()})
        await producer.send(settings.volatility_surface_topic, out)


@app.on_event("startup")
async def startup_event():
    global consumer_task
    await producer.start()
    await consumer.start()
    consumer_task = asyncio.create_task(_consume())


@app.on_event("shutdown")
async def shutdown_event():
    if consumer_task:
        consumer_task.cancel()
    await consumer.stop()
    await producer.stop()
    await redis_client.close()


@app.post("/v1/volsurface/build")
async def build(payload: VolSurfaceInput):
    out = build_surface_signal(payload)
    await redis_client.hset(f"volsurface:{payload.symbol}", mapping={k: str(v) for k, v in out.items()})
    await producer.send(settings.volatility_surface_topic, out)
    return out


@app.get("/v1/volsurface/{symbol}")
async def by_symbol(symbol: str):
    return {"symbol": symbol, "vol_surface": await redis_client.hgetall(f"volsurface:{symbol}")}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "volatility-surface-service"}
