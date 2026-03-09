import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="AuthService", version="1.0.0")
TOKEN_TTL_SECONDS = 60 * 60 * 8


class LoginIn(BaseModel):
    email: EmailStr
    password_hash: str


class RefreshIn(BaseModel):
    refresh_token: str


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/auth/login")
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db_session)):
    user = (
        await db.execute(
            text(
                """
                SELECT id, email, password_hash, status
                FROM users
                WHERE email = :email
                """
            ),
            {"email": payload.email},
        )
    ).mappings().first()
    if not user or user["password_hash"] != payload.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="User inactive")

    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)

    session_payload = {
        "user_id": str(user["id"]),
        "email": user["email"],
        "expires_at": expires_at.isoformat(),
    }
    await redis_client.hset(f"auth:access:{access_token}", mapping=session_payload)
    await redis_client.expire(f"auth:access:{access_token}", TOKEN_TTL_SECONDS)
    await redis_client.hset(f"auth:refresh:{refresh_token}", mapping={"user_id": str(user["id"])})
    await redis_client.expire(f"auth:refresh:{refresh_token}", TOKEN_TTL_SECONDS * 7)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user_id": str(user["id"]),
    }


@app.post("/v1/auth/refresh")
async def refresh(payload: RefreshIn):
    session = await redis_client.hgetall(f"auth:refresh:{payload.refresh_token}")
    if not session:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = session["user_id"]

    new_access = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    await redis_client.hset(
        f"auth:access:{new_access}",
        mapping={"user_id": user_id, "expires_at": expires_at.isoformat()},
    )
    await redis_client.expire(f"auth:access:{new_access}", TOKEN_TTL_SECONDS)

    return {"access_token": new_access, "token_type": "bearer", "expires_at": expires_at.isoformat()}


@app.post("/v1/auth/logout")
async def logout(access_token: str):
    await redis_client.delete(f"auth:access:{access_token}")
    return {"logged_out": True}


@app.get("/v1/auth/validate")
async def validate(access_token: str):
    session = await redis_client.hgetall(f"auth:access:{access_token}")
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"valid": True, "session": session}


@app.get("/v1/auth/user/{user_id}/brokers")
async def authorized_brokers(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    rows = (
        await db.execute(
            text(
                """
                SELECT broker_name, client_code, status, token_expires_at
                FROM broker_connections
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return {"user_id": str(user_id), "brokers": [dict(r) for r in rows]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-service"}
