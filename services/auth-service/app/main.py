import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="AuthService", version="2.0.0")
TOKEN_TTL_SECONDS = 60 * 60 * 8


class RegisterIn(BaseModel):
    email: EmailStr
    password_hash: str
    full_name: str | None = None
    phone: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password_hash: str


class RefreshIn(BaseModel):
    refresh_token: str


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/auth/register")
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                INSERT INTO users(email, password_hash, full_name, phone, status)
                VALUES (:email, :password_hash, :full_name, :phone, 'pending_verification')
                ON CONFLICT (email) DO NOTHING
                RETURNING id, email, status
                """
            ),
            payload.model_dump(),
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=409, detail="Email already exists")

    token = secrets.token_urlsafe(24)
    await redis_client.setex(f"verify:{token}", 3600, str(row["id"]))
    return {"user_id": str(row["id"]), "email": row["email"], "verification_token": token}


@app.post("/auth/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db_session)):
    user_id = await redis_client.get(f"verify:{token}")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    await db.execute(text("UPDATE users SET status='active', updated_at=now() WHERE id=:id"), {"id": user_id})
    await redis_client.delete(f"verify:{token}")
    return {"verified": True, "user_id": user_id}


@app.post("/auth/login")
@app.post("/v1/auth/login")
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db_session)):
    user = (
        await db.execute(
            text("SELECT id, email, password_hash, status FROM users WHERE email = :email"),
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

    await redis_client.hset(f"auth:access:{access_token}", mapping={"user_id": str(user["id"]), "email": user["email"], "expires_at": expires_at.isoformat()})
    await redis_client.expire(f"auth:access:{access_token}", TOKEN_TTL_SECONDS)
    await redis_client.hset(f"auth:refresh:{refresh_token}", mapping={"user_id": str(user["id"])})
    await redis_client.expire(f"auth:refresh:{refresh_token}", TOKEN_TTL_SECONDS * 7)

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user_id": str(user["id"]), "email": user["email"]}


@app.post("/v1/auth/refresh")
async def refresh(payload: RefreshIn):
    session = await redis_client.hgetall(f"auth:refresh:{payload.refresh_token}")
    if not session:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = session["user_id"]

    new_access = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    await redis_client.hset(f"auth:access:{new_access}", mapping={"user_id": user_id, "expires_at": expires_at.isoformat()})
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-service"}
