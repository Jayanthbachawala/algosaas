from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import PredictionInput, PredictionOutput

app = FastAPI(title="PredictionService", version="3.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


def _clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def _detect_regime(payload: PredictionInput) -> str:
    if payload.adx > 25:
        return "trending_regime"
    if payload.atr < 0.004:
        return "range_regime"
    if payload.implied_volatility > 35 or payload.volatility_surface_signal > 0.65:
        return "high_volatility_regime"
    return "low_volatility_regime"


def _strategy_for_regime(regime: str) -> str:
    return {
        "trending_regime": "atm_directional_trade",
        "range_regime": "iron_condor",
        "high_volatility_regime": "long_straddle",
        "low_volatility_regime": "short_strangle",
    }.get(regime, "atm_directional_trade")


def _ensemble_components(payload: PredictionInput) -> dict[str, float]:
    random_forest = _clip(0.5 + 0.25 * payload.oi_change + 0.15 * payload.price_momentum + 0.1 * payload.options_flow_score)
    gradient_boost = _clip(0.5 + 0.20 * (1 - abs(payload.put_call_ratio - 1)) + 0.15 * payload.gamma + 0.1 * payload.volatility_surface_signal)
    neural_network = _clip(0.5 + 0.15 * payload.implied_volatility / 50 + 0.15 * abs(payload.vwap_deviation) + 0.2 * payload.orderbook_imbalance)
    logistic_model = _clip(0.5 + 0.10 * payload.price_momentum + 0.10 * payload.oi_change - 0.15 * payload.bid_ask_spread)
    rl_agent_prediction = _clip(payload.rl_agent_output if payload.rl_agent_output > 0 else 0.5 + 0.1 * payload.options_flow_score)
    return {
        "random_forest": round(random_forest, 6),
        "gradient_boost": round(gradient_boost, 6),
        "neural_network": round(neural_network, 6),
        "logistic_model": round(logistic_model, 6),
        "rl_agent": round(rl_agent_prediction, 6),
    }


def _ensemble_probability(c: dict[str, float]) -> float:
    return round(
        0.25 * c["random_forest"]
        + 0.25 * c["gradient_boost"]
        + 0.20 * c["neural_network"]
        + 0.15 * c["logistic_model"]
        + 0.15 * c["rl_agent"],
        6,
    )


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
        return "ai-trading-brain-v3-baseline"
    return f"{row['model_name']}:{row['version']}"


@app.post("/v1/predictions/infer", response_model=PredictionOutput)
async def infer(payload: PredictionInput, db: AsyncSession = Depends(get_db_session)):
    components = _ensemble_components(payload)
    probability = _clip(_ensemble_probability(components))
    regime = _detect_regime(payload)
    strategy = _strategy_for_regime(regime)

    expected_move = round(payload.price_momentum * payload.strike * (0.05 if regime == "trending_regime" else 0.02), 2)
    spread = round(max(0.02, (1 - probability) * 0.2), 4)
    ci = (max(0.0, round(probability - spread, 4)), min(1.0, round(probability + spread, 4)))
    model_version = await _active_model_version(db)

    result = PredictionOutput(
        symbol=payload.symbol,
        probability=probability,
        market_regime=regime,
        strategy=strategy,
        ensemble_components=components,
        expected_move=expected_move,
        confidence_interval=ci,
        model_version=model_version,
    )

    event = result.model_dump()
    await redis_client.hset(
        f"prediction:{payload.symbol}:{payload.strike}:{payload.option_type}",
        mapping={k: str(v) for k, v in event.items()},
    )
    await producer.send(settings.prediction_topic, event)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "prediction-service"}
