import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/billing", tags=["billing"])
stripe.api_key = settings.STRIPE_SECRET_KEY


class CheckoutResponse(BaseModel):
    checkout_url: str


@router.get("/plan")
async def get_plan(user: User = Depends(get_current_user)):
    return {"plan": user.plan, "limits": settings.PLAN_LIMITS[user.plan]}


@router.post("/checkout/{plan}", response_model=CheckoutResponse)
async def create_checkout(plan: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if plan not in ("pro", "agency"):
        raise HTTPException(status_code=400, detail="Invalid plan")
    price_id = settings.STRIPE_PRICE_PRO if plan == "pro" else settings.STRIPE_PRICE_AGENCY
    if not price_id:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
        user.stripe_customer_id = customer.id
        await db.commit()
    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.BASE_URL}/dashboard?upgraded=true",
        cancel_url=f"{settings.BASE_URL}/dashboard",
        metadata={"user_id": str(user.id), "plan": plan},
    )
    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session["metadata"]["user_id"])
        plan = session["metadata"]["plan"]
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.plan = plan
            user.stripe_subscription_id = session.get("subscription")
            await db.commit()
    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"]["id"]
        result = await db.execute(select(User).where(User.stripe_subscription_id == sub_id))
        user = result.scalar_one_or_none()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            await db.commit()
    return {"status": "ok"}
