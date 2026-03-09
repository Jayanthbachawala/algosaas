from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import MarketTickIn

app = FastAPI(title="MarketDataService", version="1.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/market/ticks")
async def ingest_ticks(ticks: list[MarketTickIn], db: AsyncSession = Depends(get_db_session)):
    for tick in ticks:
        await db.execute(
            text(
                """
                INSERT INTO market_ticks(symbol, ts, ltp, volume, oi, bid, ask)
                VALUES (:symbol, :ts, :ltp, :volume, :oi, :bid, :ask)
                """
            ),
            tick.model_dump(),
        )
        key = f"tick:{tick.symbol}"
        await redis_client.hset(key, mapping={k: str(v) for k, v in tick.model_dump().items()})
        await producer.send(settings.market_tick_topic, tick.model_dump(mode="json"))
    return {"ingested": len(ticks)}


@app.get("/v1/market/ticks/{symbol}")
async def get_latest_tick(symbol: str, db: AsyncSession = Depends(get_db_session)):
    key = f"tick:{symbol}"
    cached = await redis_client.hgetall(key)
    if cached:
        return {"source": "redis", "tick": cached}

    row = (
        await db.execute(
            text(
                """
                SELECT symbol, ts, ltp, volume, oi, bid, ask
                FROM market_ticks
                WHERE symbol = :symbol
                ORDER BY ts DESC
                LIMIT 1
                """
            ),
            {"symbol": symbol},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Tick not found")
    return {"source": "postgres", "tick": dict(row)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "market-data-service"}
