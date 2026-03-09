import asyncio
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="APIGateway", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICES = {
    "auth": os.getenv("AUTH_SERVICE_URL", "http://localhost:8014"),
    "user": os.getenv("USER_SERVICE_URL", "http://localhost:8013"),
    "subscription": os.getenv("SUBSCRIPTION_SERVICE_URL", "http://localhost:8015"),
    "billing": os.getenv("BILLING_SERVICE_URL", "http://localhost:8016"),
    "portfolio": os.getenv("PORTFOLIO_SERVICE_URL", "http://localhost:8017"),
    "history": os.getenv("TRADE_HISTORY_SERVICE_URL", "http://localhost:8018"),
    "notification": os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8019"),
    "signal": os.getenv("SIGNAL_ENGINE_SERVICE_URL", "http://localhost:8004"),
    "market": os.getenv("MARKET_DATA_SERVICE_URL", "http://localhost:8001"),
    "broker": os.getenv("BROKER_GATEWAY_SERVICE_URL", "http://localhost:8012"),
    "prediction": os.getenv("PREDICTION_SERVICE_URL", "http://localhost:8007"),
    "risk": os.getenv("RISK_SERVICE_URL", "http://localhost:8010"),
}


async def _proxy(
    method: str,
    service: str,
    path: str,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
):
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")
    url = f"{SERVICES[service]}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(method, url, json=body, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json() if response.content else {"ok": True}


@app.post("/api/v1/auth/login")
async def login(payload: dict[str, Any]):
    return await _proxy("POST", "auth", "/v1/auth/login", body=payload)


@app.post("/api/v1/auth/refresh")
async def refresh(payload: dict[str, Any]):
    return await _proxy("POST", "auth", "/v1/auth/refresh", body=payload)


@app.get("/api/v1/users/{user_id}/profile")
async def profile(user_id: str):
    return await _proxy("GET", "user", f"/v1/users/{user_id}")


@app.get("/api/v1/dashboard/{user_id}")
async def dashboard(user_id: str):
    signals = await _proxy("GET", "signal", "/v1/signals/panel")
    portfolio = await _proxy("GET", "portfolio", f"/v1/portfolio/{user_id}/summary")
    exposure = await _proxy("GET", "portfolio", f"/v1/portfolio/{user_id}/exposure")
    orders = await _proxy("GET", "history", f"/v1/trades/{user_id}/orders", params={"limit": 20})
    subscription = await _proxy("GET", "subscription", f"/v1/subscriptions/{user_id}")
    return {
        "signals": signals,
        "portfolio": portfolio,
        "exposure": exposure,
        "orders": orders,
        "subscription": subscription,
    }


@app.post("/api/v1/trade/execute/live")
async def execute_live(payload: dict[str, Any]):
    risk = await _proxy(
        "POST",
        "risk",
        "/v1/risk/check",
        body={
            "user_id": payload["user_id"],
            "symbol": payload["symbol"],
            "quantity": payload["quantity"],
            "entry_price": payload.get("price", payload.get("entry_price", 0)),
            "implied_volatility": payload.get("implied_volatility", 0),
        },
    )
    if not risk.get("allowed"):
        return {"executed": False, "risk": risk}
    order = await _proxy("POST", "broker", "/v1/broker/orders", body=payload)
    confirmation = await _proxy(
        "GET",
        "broker",
        f"/v1/broker/orders/{payload['broker_name']}/{order['broker_order_id']}/confirmation",
        params={"user_id": payload["user_id"]},
    )
    return {"executed": True, "order": order, "risk": risk, "confirmation": confirmation}


@app.post("/api/v1/trade/execute/paper")
async def execute_paper(payload: dict[str, Any]):
    paper_url = os.getenv("PAPER_TRADING_SERVICE_URL", "http://localhost:8009")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{paper_url}/v1/paper/orders", json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.post("/api/v1/broker/oauth/connect")
async def broker_oauth_connect(payload: dict[str, Any]):
    return await _proxy("POST", "broker", "/v1/broker/oauth/connect", body=payload)


@app.get("/api/v1/broker/oauth/{broker}/callback")
async def broker_oauth_callback(broker: str, code: str = Query(...), state: str = Query(...)):
    return await _proxy(
        "GET",
        "broker",
        f"/v1/broker/oauth/{broker}/callback",
        params={"code": code, "state": state},
    )


@app.post("/api/v1/broker/auth/refresh")
async def broker_refresh(payload: dict[str, Any]):
    return await _proxy("POST", "broker", "/v1/broker/auth/refresh", body=payload)


@app.get("/api/v1/broker/{user_id}/{broker_name}/positions")
async def broker_positions(user_id: str, broker_name: str):
    return await _proxy("GET", "broker", f"/v1/broker/positions/{user_id}/{broker_name}")


@app.get("/api/v1/broker/{user_id}/{broker_name}/orders/{broker_order_id}/confirmation")
async def broker_execution_confirmation(user_id: str, broker_name: str, broker_order_id: str):
    return await _proxy(
        "GET",
        "broker",
        f"/v1/broker/orders/{broker_name}/{broker_order_id}/confirmation",
        params={"user_id": user_id},
    )


@app.websocket("/ws/market/{symbol}")
async def ws_market(websocket: WebSocket, symbol: str):
    await websocket.accept()
    market_url = SERVICES["market"]
    signal_url = SERVICES["signal"]
    try:
        while True:
            async with httpx.AsyncClient(timeout=10.0) as client:
                tick_task = client.get(f"{market_url}/v1/market/ticks/{symbol}")
                signal_task = client.get(f"{signal_url}/v1/signals/panel")
                tick_resp, signal_resp = await asyncio.gather(tick_task, signal_task)

            payload = {
                "symbol": symbol,
                "tick": tick_resp.json() if tick_resp.status_code == 200 else None,
                "signals": signal_resp.json().get("signals", [])[:5] if signal_resp.status_code == 200 else [],
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        return


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
