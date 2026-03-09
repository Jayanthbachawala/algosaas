from datetime import datetime, timezone

from fastapi import FastAPI, Query

from services.common.config import settings
from services.common.kafka_client import KafkaProducerClient
from services.common.redis_client import redis_client

app = FastAPI(title="ScannerService", version="1.0.0")
producer = KafkaProducerClient()


@app.on_event("startup")
async def startup_event() -> None:
    await producer.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await producer.stop()
    await redis_client.close()


@app.post("/v1/scanner/run")
async def run_scanner(
    momentum_threshold: float = Query(default=0.6),
    volume_spike_threshold: float = Query(default=1.3),
):
    tick_keys = await redis_client.keys("tick:*")
    opportunities: list[dict] = []

    for key in tick_keys:
        tick = await redis_client.hgetall(key)
        if not tick:
            continue
        ltp = float(tick.get("ltp", 0.0))
        bid = float(tick.get("bid", 0.0)) if tick.get("bid") else ltp
        ask = float(tick.get("ask", 0.0)) if tick.get("ask") else ltp
        volume = float(tick.get("volume", 0.0) or 0.0)

        momentum = abs((ltp - bid) / bid) if bid > 0 else 0.0
        volume_spike = (volume / 100000.0) if volume > 0 else 0.0

        if momentum >= momentum_threshold or volume_spike >= volume_spike_threshold:
            event = {
                "symbol": tick["symbol"],
                "ltp": ltp,
                "momentum": momentum,
                "volume_spike": volume_spike,
                "scanner_ts": datetime.now(timezone.utc).isoformat(),
            }
            opportunities.append(event)
            await producer.send(settings.scanner_topic, event)

    await redis_client.set("scanner:last_run_count", len(opportunities))
    return {"opportunities": opportunities, "count": len(opportunities)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scanner-service"}
