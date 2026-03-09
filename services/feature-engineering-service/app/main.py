import asyncio
from collections import deque
from datetime import datetime, timezone
from statistics import mean

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.config import settings
from services.common.kafka_client import KafkaConsumerClient, KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import EnrichedFeature

app = FastAPI(title="FeatureEngineeringService", version="3.0.0")
producer = KafkaProducerClient()
consumer = KafkaConsumerClient(settings.market_tick_topic, "feature-engineering-service")
consumer_task: asyncio.Task | None = None

PRICE_WINDOWS: dict[str, deque[float]] = {}
VOLUME_WINDOWS: dict[str, deque[float]] = {}
IV_WINDOWS: dict[str, deque[float]] = {}


class FeaturePayload(BaseModel):
    symbol: str
    strike: float = 0
    option_type: str = "CE"
    ltp: float
    oi: float = 0.0
    volume: float = 0.0
    iv: float = 0.0
    pcr: float = 1.0
    vwap: float | None = None
    bid: float | None = None
    ask: float | None = None


def _window(store: dict[str, deque[float]], key: str, value: float, maxlen: int = 50) -> deque[float]:
    dq = store.get(key)
    if dq is None:
        dq = deque(maxlen=maxlen)
        store[key] = dq
    dq.append(value)
    return dq


def _market_regime(adx: float, atr: float, iv: float) -> str:
    if adx > 25:
        return "trending_regime"
    if atr < 0.004:
        return "range_regime"
    if iv > 30:
        return "high_volatility_regime"
    return "low_volatility_regime"


def _compute(payload: FeaturePayload) -> EnrichedFeature:
    pwin = _window(PRICE_WINDOWS, payload.symbol, payload.ltp)
    vwin = _window(VOLUME_WINDOWS, payload.symbol, payload.volume)
    ivwin = _window(IV_WINDOWS, payload.symbol, payload.iv)

    prev = pwin[-2] if len(pwin) > 1 else payload.ltp
    momentum = (payload.ltp - prev) / max(prev, 1e-6)
    sma_short = mean(list(pwin)[-5:]) if len(pwin) >= 5 else payload.ltp
    sma_long = mean(pwin)
    ma_crossover = (sma_short - sma_long) / max(sma_long, 1e-6)

    atr = mean([abs(pwin[i] - pwin[i - 1]) / max(pwin[i - 1], 1e-6) for i in range(1, len(pwin))]) if len(pwin) > 2 else 0.0
    adx = min(50.0, abs(ma_crossover) * 400)

    oi_change = payload.oi / 100000
    oi_buildup = max(-1.0, min(1.0, oi_change * 5))
    max_pain_distance = abs(payload.ltp - round(payload.ltp / 50) * 50) / max(payload.ltp, 1.0)
    oi_concentration = min(1.0, abs(oi_change) * 3)

    iv_change = (ivwin[-1] - ivwin[-2]) / max(ivwin[-2], 1e-6) if len(ivwin) > 1 else 0.0
    volatility_skew = payload.pcr - 1.0
    iv_mean = mean(ivwin)
    volatility_smile = abs(payload.iv - iv_mean) / max(iv_mean, 1e-6)
    volatility_term_structure = (ivwin[-1] - ivwin[0]) / max(ivwin[0], 1e-6) if len(ivwin) > 3 else 0.0
    volatility_expansion = 1.0 if iv_change > 0.1 else 0.0

    delta_imbalance = max(-1.0, min(1.0, momentum * 2))
    gamma_exposure = min(1.0, abs(momentum) * 5)
    theta_decay_pattern = min(1.0, payload.iv / 100)
    vega_sensitivity = min(1.0, abs(iv_change) * 2)

    bid = payload.bid if payload.bid is not None else payload.ltp
    ask = payload.ask if payload.ask is not None else payload.ltp
    bid_ask_spread = (ask - bid) / max(payload.ltp, 1e-6)
    orderbook_imbalance = (payload.ltp - bid) / max((ask - bid) if ask > bid else payload.ltp, 1e-6)
    avg_vol = mean(vwin)
    volume_spike = payload.volume / max(avg_vol, 1)

    vwap = payload.vwap or payload.ltp
    regime = _market_regime(adx, atr, payload.iv)

    return EnrichedFeature(
        symbol=payload.symbol,
        strike=payload.strike,
        option_type="CE" if payload.option_type not in {"CE", "PE"} else payload.option_type,
        ts=datetime.now(timezone.utc).isoformat(),
        price_momentum=round(momentum, 6),
        vwap_deviation=round((payload.ltp - vwap) / max(vwap, 1e-6), 6),
        atr=round(atr, 6),
        adx=round(adx, 6),
        oi_change=round(oi_change, 6),
        oi_buildup_score=round(oi_buildup, 6),
        put_call_ratio=payload.pcr,
        max_pain_distance=round(max_pain_distance, 6),
        oi_concentration_score=round(oi_concentration, 6),
        implied_volatility=payload.iv,
        iv_change=round(iv_change, 6),
        volatility_skew=round(volatility_skew, 6),
        volatility_smile=round(volatility_smile, 6),
        volatility_term_structure=round(volatility_term_structure, 6),
        volatility_expansion=round(volatility_expansion, 6),
        delta_imbalance=round(delta_imbalance, 6),
        gamma_exposure=round(gamma_exposure, 6),
        theta_decay_pattern=round(theta_decay_pattern, 6),
        vega_sensitivity=round(vega_sensitivity, 6),
        bid_ask_spread=round(bid_ask_spread, 6),
        orderbook_imbalance=round(orderbook_imbalance, 6),
        volume_spike=round(volume_spike, 6),
        market_regime=regime,
    )


async def _publish(enriched: EnrichedFeature):
    d = enriched.model_dump()
    await redis_client.hset(f"features:{enriched.symbol}", mapping={k: str(v) for k, v in d.items()})
    await producer.send(settings.features_topic, d)
    await producer.send(settings.features_enriched_topic, d)


async def _consume_market_ticks() -> None:
    async for m in consumer.messages():
        if not m.get("symbol"):
            continue
        enriched = _compute(
            FeaturePayload(
                symbol=m["symbol"],
                ltp=float(m.get("ltp", 0.0)),
                oi=float(m.get("oi", 0.0) or 0.0),
                volume=float(m.get("volume", 0.0) or 0.0),
                iv=float(m.get("iv", 0.0) or 0.0),
                pcr=float(m.get("pcr", 1.0) or 1.0),
                bid=float(m.get("bid", 0.0) or 0.0),
                ask=float(m.get("ask", 0.0) or 0.0),
            )
        )
        await _publish(enriched)


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
    enriched = _compute(payload)
    await _publish(enriched)
    return enriched


@app.get("/v1/features/{symbol}")
async def latest_features(symbol: str):
    return {"symbol": symbol, "features": await redis_client.hgetall(f"features:{symbol}")}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "feature-engineering-service"}
