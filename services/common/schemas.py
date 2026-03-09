from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class MarketTickIn(BaseModel):
    symbol: str
    ts: datetime
    ltp: float
    volume: int | None = None
    oi: int | None = None
    bid: float | None = None
    ask: float | None = None


class OptionChainSnapshotIn(BaseModel):
    underlying_symbol: str
    expiry_date: date
    strike: float
    option_type: Literal["CE", "PE"]
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    oi: int | None = None
    oi_change: int | None = None
    pcr: float | None = None
    snapshot_ts: datetime


class EnrichedFeature(BaseModel):
    symbol: str
    strike: float = 0
    option_type: Literal["CE", "PE"] = "CE"
    ts: str
    price_momentum: float
    vwap_deviation: float
    atr: float
    adx: float
    oi_change: float
    oi_buildup_score: float
    put_call_ratio: float
    max_pain_distance: float
    oi_concentration_score: float
    implied_volatility: float
    iv_change: float
    volatility_skew: float
    volatility_smile: float
    volatility_term_structure: float
    volatility_expansion: float
    delta_imbalance: float
    gamma_exposure: float
    theta_decay_pattern: float
    vega_sensitivity: float
    bid_ask_spread: float
    orderbook_imbalance: float
    volume_spike: float
    market_regime: str


class SignalInput(BaseModel):
    user_id: str | None = None
    symbol: str
    strike: float
    option_type: Literal["CE", "PE"]
    entry_price: float

    oi_change: float
    oi_buildup_score: float = 0.0
    max_pain_distance: float = 0.0
    put_call_ratio: float
    oi_concentration_score: float = 0.0

    implied_volatility: float
    iv_change: float = 0.0
    volatility_skew: float = 0.0
    volatility_smile: float = 0.0
    volatility_term_structure: float = 0.0
    volatility_expansion: float = 0.0

    delta: float
    gamma: float
    theta: float
    vega: float
    delta_imbalance: float = 0.0
    gamma_spike: float = 0.0
    theta_decay_pattern: float = 0.0
    vega_exposure: float = 0.0

    price_momentum: float
    moving_average_crossover: float = 0.0
    atr_breakout: float = 0.0
    vwap_deviation: float

    bid_ask_spread: float = 0.0
    orderbook_imbalance: float = 0.0
    volume_spike: float

    adx: float = 0.0
    atr: float = 0.0

    options_flow_score: float = 0.0
    volatility_surface_signal: float = 0.0
    rl_agent_output: float = 0.0
    market_regime_alignment: float = 0.0


class SignalOut(BaseModel):
    symbol: str
    strike: float
    option_type: Literal["CE", "PE"]
    entry_price: float
    stop_loss: float
    target: float
    probability: float = Field(ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"]
    strategy: str
    market_regime: str
    final_score: float = Field(ge=0.0, le=1.0)


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
    adx: float = 0.0
    atr: float = 0.0
    bid_ask_spread: float = 0.0
    orderbook_imbalance: float = 0.0
    options_flow_score: float = 0.0
    volatility_surface_signal: float = 0.0
    rl_agent_output: float = 0.0


class PredictionOutput(BaseModel):
    symbol: str
    probability: float = Field(ge=0.0, le=1.0)
    market_regime: str
    strategy: str
    ensemble_components: dict
    expected_move: float
    confidence_interval: tuple[float, float]
    model_version: str
