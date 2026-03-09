import random
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.database import get_db_session
from services.common.redis_client import redis_client

app = FastAPI(title="BillingService", version="1.0.0")


class InvoiceIn(BaseModel):
    user_id: UUID
    subscription_id: UUID | None = None
    amount_paise: int
    payment_provider: str = "Razorpay"


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await redis_client.close()


@app.post("/v1/billing/invoices")
async def create_invoice(payload: InvoiceIn, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                INSERT INTO billing_invoices(user_id, subscription_id, amount_paise, payment_provider, status, payment_ref)
                VALUES (:user_id, :subscription_id, :amount_paise, :payment_provider, 'issued', :payment_ref)
                RETURNING id, user_id, subscription_id, amount_paise, currency, payment_provider, payment_ref, status, issued_at
                """
            ),
            {
                "user_id": payload.user_id,
                "subscription_id": payload.subscription_id,
                "amount_paise": payload.amount_paise,
                "payment_provider": payload.payment_provider,
                "payment_ref": f"pay_{random.randint(100000,999999)}",
            },
        )
    ).mappings().one()
    await redis_client.hset(f"invoice:{row['id']}", mapping={k: str(v) for k, v in dict(row).items()})
    return dict(row)


@app.post("/v1/billing/invoices/{invoice_id}/pay")
async def pay_invoice(invoice_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            text(
                """
                UPDATE billing_invoices
                SET status = 'paid', paid_at = now()
                WHERE id = :invoice_id
                RETURNING id, user_id, amount_paise, currency, payment_provider, payment_ref, status, paid_at
                """
            ),
            {"invoice_id": invoice_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")

    await redis_client.hset(f"invoice:{invoice_id}", mapping={k: str(v) for k, v in dict(row).items()})
    return dict(row)


@app.get("/v1/billing/users/{user_id}/invoices")
async def user_invoices(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    rows = (
        await db.execute(
            text(
                """
                SELECT id, amount_paise, currency, payment_provider, status, issued_at, paid_at
                FROM billing_invoices
                WHERE user_id = :user_id
                ORDER BY issued_at DESC
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return {"user_id": str(user_id), "invoices": [dict(r) for r in rows], "count": len(rows)}


@app.get("/v1/billing/revenue/today")
async def revenue_today(db: AsyncSession = Depends(get_db_session)):
    total = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sum(amount_paise),0)
                FROM billing_invoices
                WHERE status = 'paid' AND paid_at::date = CURRENT_DATE
                """
            )
        )
    ).scalar_one()
    now = datetime.now(timezone.utc).isoformat()
    return {"date": now, "paid_revenue_paise": int(total)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "billing-service"}
