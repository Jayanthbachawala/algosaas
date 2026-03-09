import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.config import settings
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="OrderFlowService", version="1.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.features_enriched_topic, "order-flow-service")
consumer_task: asyncio.Task | None = None


class OrderFlowInput(BaseModel):
    symbol: str
    large_trade_blocks: float = 0
    iceberg_pattern_score: float = 0
    liquidity_withdrawal_score: float = 0
    orderbook_imbalance: float = 0


def detect_orderflow(payload: OrderFlowInput) -> dict:
    accumulation = (
        payload.large_trade_blocks * 0.35
        + payload.iceberg_pattern_score * 0.25
        + max(payload.orderbook_imbalance, 0) * 0.20
        + payload.liquidity_withdrawal_score * 0.20
    )
    distribution = (
        payload.large_trade_blocks * 0.25
        + payload.iceberg_pattern_score * 0.25
        + max(-payload.orderbook_imbalance, 0) * 0.30
        + payload.liquidity_withdrawal_score * 0.20
    )
    institutional_accumulation = min(1.0, accumulation)
    institutional_distribution = min(1.0, distribution)
    return {
        "symbol": payload.symbol,
        "institutional_accumulation": round(institutional_accumulation, 6),
        "institutional_distribution": round(institutional_distribution, 6),
        "orderflow_signal": "institutional_accumulation" if institutional_accumulation >= institutional_distribution else "institutional_distribution",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _consume():
    async for m in consumer.messages():
        out = detect_orderflow(
            OrderFlowInput(
                symbol=m.get("symbol", "UNKNOWN"),
                large_trade_blocks=float(m.get("oi_concentration_score", 0) or 0),
                iceberg_pattern_score=float(m.get("volume_spike", 0) or 0) / 5,
                liquidity_withdrawal_score=float(m.get("bid_ask_spread", 0) or 0) * 10,
                orderbook_imbalance=float(m.get("orderbook_imbalance", 0) or 0),
            )
        )
        await redis_client.hset(f"orderflow:{out['symbol']}", mapping={k: str(v) for k, v in out.items()})
        await producer.send(settings.orderflow_signal_topic, out)


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


@app.post("/v1/orderflow/detect")
async def detect(payload: OrderFlowInput):
    out = detect_orderflow(payload)
    await redis_client.hset(f"orderflow:{payload.symbol}", mapping={k: str(v) for k, v in out.items()})
    await producer.send(settings.orderflow_signal_topic, out)
    return out


@app.get("/v1/orderflow/{symbol}")
async def by_symbol(symbol: str):
    return {"symbol": symbol, "orderflow": await redis_client.hgetall(f"orderflow:{symbol}")}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "order-flow-service"}
