import json

import httpx
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import PredictionInput, SignalInput, SignalOut

app = FastAPI(title="SignalEngineService", version="3.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


def _normalize(value: float, min_v: float = -1.0, max_v: float = 1.0) -> float:
    clipped = max(min_v, min(max_v, value))
    return (clipped - min_v) / (max_v - min_v) if max_v != min_v else 0


def _confidence(probability: float) -> str:
    if probability >= 0.82:
        return "high"
    if probability >= 0.70:
        return "medium"
    return "low"


async def _fetch_prediction(payload: SignalInput) -> dict:
    infer_input = PredictionInput(
        symbol=payload.symbol,
        strike=payload.strike,
        option_type=payload.option_type,
        oi_change=payload.oi_change,
        put_call_ratio=payload.put_call_ratio,
        implied_volatility=payload.implied_volatility,
        delta=payload.delta,
        gamma=payload.gamma,
        theta=payload.theta,
        vega=payload.vega,
        price_momentum=payload.price_momentum,
        volume_spike=payload.volume_spike,
        vwap_deviation=payload.vwap_deviation,
        adx=payload.adx,
        atr=payload.atr,
        bid_ask_spread=payload.bid_ask_spread,
        orderbook_imbalance=payload.orderbook_imbalance,
        options_flow_score=payload.options_flow_score,
        volatility_surface_signal=payload.volatility_surface_signal,
        rl_agent_output=payload.rl_agent_output,
    ).model_dump()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{settings.prediction_service_url}/v1/predictions/infer", json=infer_input)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def _risk_check(payload: SignalInput) -> dict:
    if not payload.user_id:
        return {"allowed": True, "mode": "no_user_context"}
    risk_payload = {
        "user_id": payload.user_id,
        "symbol": payload.symbol,
        "quantity": 50,
        "entry_price": payload.entry_price,
        "implied_volatility": payload.implied_volatility,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{settings.risk_service_url}/v1/risk/check", json=risk_payload)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def _overlay_intelligence(payload: SignalInput) -> SignalInput:
    of = await redis_client.hgetall(f"optionsflow:{payload.symbol}")
    vs = await redis_client.hgetall(f"volsurface:{payload.symbol}")
    rl = await redis_client.hgetall(f"rl:last:{payload.symbol}")
    # market regime alignment proxy from enriched features
    regime_alignment = 1.0 if payload.adx > 25 and payload.price_momentum > 0 else 0.5
    return payload.model_copy(
        update={
            "options_flow_score": float(of.get("options_flow_score", payload.options_flow_score)),
            "volatility_surface_signal": float(vs.get("vol_surface_signal", payload.volatility_surface_signal)),
            "rl_agent_output": max(0.0, min(1.0, 0.5 + float(rl.get("reward", 0)) / 10000)) if rl else payload.rl_agent_output,
            "market_regime_alignment": regime_alignment,
        }
    )


@app.post("/v1/signals/generate", response_model=SignalOut)
async def generate_signal(payload: SignalInput, db: AsyncSession = Depends(get_db_session)):
    payload = await _overlay_intelligence(payload)
    prediction = await _fetch_prediction(payload)

    ensemble_prediction = float(prediction["probability"])
    options_flow_score = payload.options_flow_score
    vol_surface_signal = payload.volatility_surface_signal
    rl_agent_output = payload.rl_agent_output
    liquidity_score = (
        _normalize(1 - payload.bid_ask_spread, 0, 1) * 0.6
        + _normalize(payload.volume_spike / 3, 0, 1) * 0.4
    )

    final_score = round(
        0.30 * ensemble_prediction
        + 0.20 * options_flow_score
        + 0.20 * vol_surface_signal
        + 0.15 * rl_agent_output
        + 0.10 * liquidity_score
        + 0.05 * payload.market_regime_alignment,
        6,
    )

    if final_score < 0.75:
        raise HTTPException(status_code=422, detail=f"Signal rejected: final_score {final_score}")

    risk_result = await _risk_check(payload)
    if not risk_result.get("allowed", False):
        raise HTTPException(status_code=422, detail=f"Risk filter rejection: {risk_result}")

    regime = prediction["market_regime"]
    strategy = prediction["strategy"]
    rr = 2.2 if regime in {"trending_regime", "high_volatility_regime"} else 1.6
    stop_loss = round(payload.entry_price * (0.82 if regime == "high_volatility_regime" else 0.86), 2)
    target = round(payload.entry_price + (payload.entry_price - stop_loss) * rr, 2)

    signal = SignalOut(
        symbol=payload.symbol,
        strike=payload.strike,
        option_type=payload.option_type,
        entry_price=payload.entry_price,
        stop_loss=stop_loss,
        target=target,
        probability=ensemble_prediction,
        confidence=_confidence(ensemble_prediction),
        strategy=strategy,
        market_regime=regime,
        final_score=final_score,
    )

    decision_context = {
        "signal_input": payload.model_dump(),
        "prediction": prediction,
        "weights": {
            "ensemble_prediction": 0.30,
            "options_flow_score": 0.20,
            "volatility_surface_signal": 0.20,
            "rl_agent_output": 0.15,
            "liquidity_score": 0.10,
            "market_regime_alignment": 0.05,
        },
        "components": {
            "ensemble_prediction": ensemble_prediction,
            "options_flow_score": options_flow_score,
            "vol_surface_signal": vol_surface_signal,
            "rl_agent_output": rl_agent_output,
            "liquidity_score": liquidity_score,
            "market_regime_alignment": payload.market_regime_alignment,
        },
        "risk": risk_result,
        "final_score": final_score,
        "signal": signal.model_dump(),
    }

    await db.execute(
        text(
            """
            INSERT INTO signals(user_id, symbol, strike, option_type, entry_price, stop_loss, target_price, probability_score, signal_payload)
            VALUES (:user_id, :symbol, :strike, :option_type, :entry_price, :stop_loss, :target_price, :probability_score, CAST(:signal_payload as jsonb))
            """
        ),
        {
            "user_id": payload.user_id,
            "symbol": signal.symbol,
            "strike": signal.strike,
            "option_type": signal.option_type,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target,
            "probability_score": signal.probability,
            "signal_payload": json.dumps(decision_context),
        },
    )

    await redis_client.hset(
        f"signal:{signal.symbol}:{signal.strike}:{signal.option_type}",
        mapping={k: str(v) for k, v in signal.model_dump().items()},
    )
    await producer.send(settings.signal_topic, signal.model_dump())
    return signal


@app.get("/v1/signals/panel")
async def signal_panel(limit: int = 50):
    keys = await redis_client.keys("signal:*")
    return {"count": min(len(keys), limit), "signals": [await redis_client.hgetall(k) for k in keys[:limit]]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "signal-engine-service"}
