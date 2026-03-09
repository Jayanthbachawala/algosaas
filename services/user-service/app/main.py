from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="UserService", version="1.0.0")


class UserCreateIn(BaseModel):
    email: EmailStr
    password_hash: str
    full_name: str | None = None
    phone: str | None = None


class UserUpdateIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    mfa_enabled: bool | None = None
    status: str | None = None


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/users")
async def create_user(payload: UserCreateIn, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                INSERT INTO users(email, password_hash, full_name, phone)
                VALUES (:email, :password_hash, :full_name, :phone)
                RETURNING id, email, full_name, phone, role, mfa_enabled, status, created_at
                """
            ),
            payload.model_dump(),
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=500, detail="User creation failed")
    await redis_client.hset(f"user:{row['id']}", mapping={k: str(v) for k, v in dict(row).items()})
    return dict(row)


@app.get("/v1/users/{user_id}")
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    cached = await redis_client.hgetall(f"user:{user_id}")
    if cached:
        return {"source": "redis", "user": cached}

    row = (
        await db.execute(
            text(
                """
                SELECT id, email, full_name, phone, role, mfa_enabled, status, created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"source": "postgres", "user": dict(row)}


@app.patch("/v1/users/{user_id}")
async def update_user(user_id: UUID, payload: UserUpdateIn, db: AsyncSession = Depends(get_db_session)):
    existing = (
        await db.execute(text("SELECT id FROM users WHERE id = :user_id"), {"user_id": user_id})
    ).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    data = payload.model_dump(exclude_none=True)
    if not data:
        return {"updated": False, "reason": "no_fields"}

    set_clause = ", ".join([f"{k} = :{k}" for k in data.keys()]) + ", updated_at = now()"
    data["user_id"] = user_id
    row = (
        await db.execute(
            text(
                f"""
                UPDATE users
                SET {set_clause}
                WHERE id = :user_id
                RETURNING id, email, full_name, phone, role, mfa_enabled, status, updated_at
                """
            ),
            data,
        )
    ).mappings().one()
    await redis_client.hset(f"user:{user_id}", mapping={k: str(v) for k, v in dict(row).items()})
    return dict(row)


@app.get("/v1/users/{user_id}/integrations")
async def user_integrations(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    brokers = (
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
    latest_signal = (
        await db.execute(
            text(
                """
                SELECT symbol, strike, option_type, entry_price, stop_loss, target_price, probability_score, generated_at
                FROM signals
                WHERE user_id = :user_id OR user_id IS NULL
                ORDER BY generated_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()

    return {
        "user_id": str(user_id),
        "broker_connections": [dict(row) for row in brokers],
        "latest_signal": dict(latest_signal) if latest_signal else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "user-service"}
