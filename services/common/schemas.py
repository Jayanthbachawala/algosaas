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


class SignalInput(BaseModel):
    symbol: str
    strike: float
    option_type: Literal["CE", "PE"]
    entry_price: float
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


class SignalOut(BaseModel):
    symbol: str
    strike: float
    option_type: Literal["CE", "PE"]
    entry_price: float
    stop_loss: float
    target: float
    ai_probability_score: float = Field(ge=0.0, le=1.0)
