from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.config import settings
from services.common.database import get_db_session
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client
from services.common.schemas import OptionChainSnapshotIn

app = FastAPI(title="OptionChainService", version="1.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/option-chain/snapshots")
async def ingest_option_chain(
    snapshots: list[OptionChainSnapshotIn], db: AsyncSession = Depends(get_db_session)
):
    for snapshot in snapshots:
        payload = snapshot.model_dump()
        await db.execute(
            text(
                """
                INSERT INTO option_chain_snapshots(
                    underlying_symbol, expiry_date, strike, option_type, iv,
                    delta, gamma, theta, vega, rho, oi, oi_change, pcr, snapshot_ts
                ) VALUES (
                    :underlying_symbol, :expiry_date, :strike, :option_type, :iv,
                    :delta, :gamma, :theta, :vega, :rho, :oi, :oi_change, :pcr, :snapshot_ts
                )
                """
            ),
            payload,
        )

        redis_key = f"oc:{snapshot.underlying_symbol}:{snapshot.expiry_date}:{snapshot.strike}:{snapshot.option_type}"
        await redis_client.hset(redis_key, mapping={k: str(v) for k, v in payload.items()})
        await producer.send(settings.option_chain_topic, snapshot.model_dump(mode="json"))

    return {"ingested": len(snapshots)}


@app.get("/v1/option-chain/{underlying_symbol}/{expiry_date}")
async def get_option_chain(underlying_symbol: str, expiry_date: str, limit: int = 100):
    keys = await redis_client.keys(f"oc:{underlying_symbol}:{expiry_date}:*")
    records = []
    for key in keys[:limit]:
        records.append(await redis_client.hgetall(key))
    return {"count": len(records), "snapshots": records}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "option-chain-service"}
