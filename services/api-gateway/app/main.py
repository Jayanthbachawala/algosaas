import asyncio
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="APIGateway", version="3.0.0")
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
    "options_flow": os.getenv("OPTIONS_FLOW_SERVICE_URL", "http://localhost:8021"),
    "vol_surface": os.getenv("VOLATILITY_SURFACE_SERVICE_URL", "http://localhost:8022"),
    "order_flow": os.getenv("ORDER_FLOW_SERVICE_URL", "http://localhost:8023"),
    "admin": os.getenv("ADMIN_SERVICE_URL", "http://localhost:8024"),
}


async def _proxy(method: str, service: str, path: str, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None):
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")
    url = f"{SERVICES[service]}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(method, url, json=body, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json() if response.content else {"ok": True}


async def _require_feature(user_id: str, feature_key: str):
    ent = await _proxy("GET", "subscription", f"/v1/subscriptions/{user_id}/entitlements")
    if not ent.get("features", {}).get(feature_key, False):
        raise HTTPException(status_code=403, detail=f"Feature '{feature_key}' not enabled")


@app.post("/api/v1/auth/register")
async def register(payload: dict[str, Any]):
    return await _proxy("POST", "auth", "/auth/register", body=payload)


@app.post("/api/v1/auth/login")
async def login(payload: dict[str, Any]):
    return await _proxy("POST", "auth", "/auth/login", body=payload)


@app.get("/api/v1/plans")
async def plans():
    return await _proxy("GET", "subscription", "/plans")


@app.post("/api/v1/subscribe")
async def subscribe(payload: dict[str, Any]):
    return await _proxy("POST", "subscription", "/subscribe", body=payload)


@app.get("/api/v1/users/{user_id}/profile")
async def profile(user_id: str):
    return await _proxy("GET", "user", f"/v1/users/{user_id}")


@app.get("/api/v1/dashboard/{user_id}")
async def dashboard(user_id: str):
    signals = await _proxy("GET", "signal", "/v1/signals/panel")
    portfolio = await _proxy("GET", "portfolio", f"/v1/portfolio/{user_id}/summary")
    exposure = await _proxy("GET", "portfolio", f"/v1/portfolio/{user_id}/exposure")
    orders = await _proxy("GET", "history", f"/v1/trades/{user_id}/orders", params={"limit": 20})
    subscription = await _proxy("GET", "subscription", f"/v1/subscriptions/{user_id}/entitlements")
    ai_insights = await _proxy("GET", "brain", f"/api/v1/brain/NIFTY") if False else {}
    return {"signals": signals, "portfolio": portfolio, "exposure": exposure, "orders": orders, "subscription": subscription, "ai_insights": ai_insights}


@app.post("/api/v1/trade/execute/live")
async def execute_live(payload: dict[str, Any]):
    await _require_feature(str(payload["user_id"]), "auto_trading")
    risk = await _proxy("POST", "risk", "/v1/risk/check", body={"user_id": payload["user_id"], "symbol": payload["symbol"], "quantity": payload["quantity"], "entry_price": payload.get("price", payload.get("entry_price", 0)), "implied_volatility": payload.get("implied_volatility", 0), "bid_ask_spread": payload.get("bid_ask_spread", 0)})
    if not risk.get("allowed"):
        return {"executed": False, "risk": risk}
    order = await _proxy("POST", "broker", "/v1/broker/orders", body=payload)
    return {"executed": True, "order": order, "risk": risk}


@app.post("/api/v1/trade/execute/paper")
async def execute_paper(payload: dict[str, Any]):
    await _require_feature(str(payload["user_id"]), "paper_trading")
    paper_url = os.getenv("PAPER_TRADING_SERVICE_URL", "http://localhost:8009")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{paper_url}/v1/paper/orders", json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/api/v1/brain/{symbol}")
async def brain_context(symbol: str):
    options_flow = await _proxy("GET", "options_flow", f"/v1/options-flow/{symbol}")
    vol_surface = await _proxy("GET", "vol_surface", f"/v1/volsurface/{symbol}")
    order_flow = await _proxy("GET", "order_flow", f"/v1/orderflow/{symbol}")
    return {"symbol": symbol, "options_flow": options_flow, "vol_surface": vol_surface, "order_flow": order_flow}


@app.post("/api/v1/notifications/send")
async def send_notification(payload: dict[str, Any]):
    return await _proxy("POST", "notification", "/v1/notifications/send", body=payload)


@app.get("/api/v1/notifications/user/{user_id}")
async def user_notifications(user_id: str):
    return await _proxy("GET", "notification", f"/v1/notifications/{user_id}")


# Admin routes
@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    return await _proxy("GET", "admin", "/v1/admin/dashboard")


@app.get("/api/v1/admin/users")
async def admin_users():
    return await _proxy("GET", "admin", "/v1/admin/users")


@app.post("/api/v1/admin/disable-trading")
async def disable_trading():
    return await _proxy("POST", "admin", "/admin/disable-trading")


@app.post("/api/v1/admin/enable-trading")
async def enable_trading():
    return await _proxy("POST", "admin", "/admin/enable-trading")


@app.get("/api/v1/admin/monitoring")
async def admin_monitoring():
    return await _proxy("GET", "admin", "/v1/admin/monitoring")


@app.get("/api/v1/admin/signals/performance")
async def signal_performance():
    return await _proxy("GET", "admin", "/v1/admin/signals/performance")


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
            await websocket.send_json({"symbol": symbol, "tick": tick_resp.json() if tick_resp.status_code == 200 else None, "signals": signal_resp.json().get("signals", [])[:5] if signal_resp.status_code == 200 else []})
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        return


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
