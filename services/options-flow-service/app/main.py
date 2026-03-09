import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.config import settings
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="OptionsFlowService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.features_enriched_topic, "options-flow-service")
consumer_task: asyncio.Task | None = None


class OptionsFlowInput(BaseModel):
    symbol: str
    call_volume: float = 0
    put_volume: float = 0
    oi_change: float = 0
    price_momentum: float = 0
    block_trade_size: float = 0


def compute_options_flow_score(payload: OptionsFlowInput) -> dict:
    vol_total = max(payload.call_volume + payload.put_volume, 1)
    cp_imbalance = (payload.call_volume - payload.put_volume) / vol_total
    unusual_activity = min(1.0, vol_total / 100000)
    oi_vs_price = payload.oi_change * (1 if payload.price_momentum >= 0 else -1)
    block_trade = min(1.0, payload.block_trade_size / 5000)

    score = max(-1.0, min(1.0, 0.35 * cp_imbalance + 0.25 * unusual_activity + 0.25 * oi_vs_price + 0.15 * block_trade))
    signal = "bullish_flow" if score > 0.2 else "bearish_flow" if score < -0.2 else "neutral_flow"
    gamma_squeeze_potential = 1 if (cp_imbalance > 0.4 and unusual_activity > 0.5) else 0
    return {
        "symbol": payload.symbol,
        "options_flow_score": round((score + 1) / 2, 6),
        "flow_signal": signal,
        "gamma_squeeze_potential": gamma_squeeze_potential,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _consume():
    async for m in consumer.messages():
        data = compute_options_flow_score(
            OptionsFlowInput(
                symbol=m.get("symbol", "UNKNOWN"),
                call_volume=float(m.get("volume_spike", 0)) * 8000,
                put_volume=float(m.get("put_call_ratio", 1)) * 4000,
                oi_change=float(m.get("oi_change", 0)),
                price_momentum=float(m.get("price_momentum", 0)),
                block_trade_size=float(m.get("oi_concentration_score", 0)) * 8000,
            )
        )
        await redis_client.hset(f"optionsflow:{data['symbol']}", mapping={k: str(v) for k, v in data.items()})
        await producer.send(settings.options_flow_topic, data)


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


@app.post("/v1/options-flow/analyze")
async def analyze(payload: OptionsFlowInput):
    out = compute_options_flow_score(payload)
    await redis_client.hset(f"optionsflow:{payload.symbol}", mapping={k: str(v) for k, v in out.items()})
    await producer.send(settings.options_flow_topic, out)
    return out


@app.get("/v1/options-flow/{symbol}")
async def by_symbol(symbol: str):
    return {"symbol": symbol, "options_flow": await redis_client.hgetall(f"optionsflow:{symbol}")}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "options-flow-service"}
