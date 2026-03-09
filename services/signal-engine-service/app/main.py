from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import SignalInput, SignalOut

app = FastAPI(title="SignalEngineService", version="1.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


def _probability(signal: SignalInput) -> float:
    score = 0.0
    score += 0.20 * min(max(signal.oi_change / 10.0, -1), 1)
    score += 0.15 * (1 - min(abs(signal.put_call_ratio - 1.0), 1.0))
    score += 0.10 * min(signal.implied_volatility / 100.0, 1.0)
    score += 0.10 * min(abs(signal.delta), 1.0)
    score += 0.15 * min(abs(signal.price_momentum), 1.0)
    score += 0.15 * min(signal.volume_spike / 3.0, 1.0)
    score += 0.15 * (1 - min(abs(signal.vwap_deviation), 1.0))
    prob = max(0.0, min(1.0, 0.5 + score / 2))
    return round(prob, 4)


@app.post("/v1/signals/generate", response_model=SignalOut)
async def generate_signal(payload: SignalInput, db: AsyncSession = Depends(get_db_session)):
    probability = _probability(payload)
    rr = 2.0
    stop_loss = round(payload.entry_price * 0.85, 2)
    target = round(payload.entry_price + (payload.entry_price - stop_loss) * rr, 2)

    signal = SignalOut(
        symbol=payload.symbol,
        strike=payload.strike,
        option_type=payload.option_type,
        entry_price=payload.entry_price,
        stop_loss=stop_loss,
        target=target,
        ai_probability_score=probability,
    )

    db_payload = {
        "symbol": signal.symbol,
        "strike": signal.strike,
        "option_type": signal.option_type,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "target_price": signal.target,
        "probability_score": signal.ai_probability_score,
        "signal_payload": payload.model_dump_json(),
    }

    await db.execute(
        text(
            """
            INSERT INTO signals(symbol, strike, option_type, entry_price, stop_loss, target_price, probability_score, signal_payload)
            VALUES (:symbol, :strike, :option_type, :entry_price, :stop_loss, :target_price, :probability_score, CAST(:signal_payload as jsonb))
            """
        ),
        db_payload,
    )

    panel_key = f"signal:{signal.symbol}:{signal.strike}:{signal.option_type}"
    await redis_client.hset(panel_key, mapping={k: str(v) for k, v in signal.model_dump().items()})
    await producer.send(settings.signal_topic, signal.model_dump())

    return signal


@app.get("/v1/signals/panel")
async def signal_panel(limit: int = 50):
    keys = await redis_client.keys("signal:*")
    entries = []
    for key in keys[:limit]:
        entries.append(await redis_client.hgetall(key))
    return {"count": len(entries), "signals": entries}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "signal-engine-service"}
