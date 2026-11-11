from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.database import get_db
from apps.api.models import StoreSettings
from apps.api.pricing import PricingEngine, PricingRequest, PriceBreakdown
from apps.api.schemas import StoreSettingsOut
from apps.api.config import settings
from apps.api.security import verify_telegram_init_data

router = APIRouter(prefix="/pricing", tags=["pricing"])

@router.get("/settings", response_model=StoreSettingsOut)
async def get_pricing_settings(request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=500, detail="Настройки магазина не найдены")
    if settings.DEV_AUTH_ENABLED or verify_telegram_init_data(request.headers.get("X-Telegram-Init-Data", ""), settings.BOT_TOKEN):
        return st
    private = dict.fromkeys(("payment_bank_name", "payment_phone", "payment_card_number", "payment_recipient_name", "payment_instructions"), "")
    return StoreSettingsOut.model_validate(st).model_copy(update=private)

@router.post("/estimate", response_model=PriceBreakdown)
async def calculate_estimate(req: PricingRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=500, detail="Настройки магазина не найдены")

    if st.exchange_rate <= 0 and not req.custom_exchange_rate:
        raise HTTPException(409, "Магазин ещё настраивает курс юаня.")
    rate = req.custom_exchange_rate if req.custom_exchange_rate else st.exchange_rate

    try:
        breakdown = PricingEngine.calculate(
            cny_price=req.cny_price,
            exchange_rate=rate,
            weight_kg=req.weight_kg or Decimal("1.20"),
            shipping_rub_per_kg=st.shipping_rub_per_kg,
            shipping_min_weight_kg=st.shipping_min_weight_kg,
            commission_type=st.commission_type,
            commission_value=st.commission_value,
            commission_fixed_bonus=st.commission_fixed_bonus or Decimal("0.00"),
            russia_shipping_type=st.russia_shipping_type,
            russia_shipping_cost=st.russia_shipping_cost,
            delivery_city=req.city or "Москва"
        )
        return breakdown
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
