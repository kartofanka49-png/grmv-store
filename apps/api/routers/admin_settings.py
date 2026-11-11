import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.database import get_db
from apps.api.models import StoreSettings, ExchangeRateAudit, User
from apps.api.schemas import (
    StoreSettingsOut, ExchangeRateUpdate, ShippingSettingsUpdate,
    CommissionSettingsUpdate, RussiaShippingSettingsUpdate, PaymentSettingsUpdate
)
from apps.api.security import get_current_admin

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

@router.get("", response_model=StoreSettingsOut)
async def get_settings(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")
    return st

@router.put("/exchange-rate", response_model=StoreSettingsOut)
async def update_exchange_rate(
    req: ExchangeRateUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")

    old_val = st.exchange_rate
    new_val = req.exchange_rate

    # Audit log entry for exchange rate
    audit = ExchangeRateAudit(
        old_rate=old_val,
        new_rate=new_val,
        changed_by=admin.username or f"ID:{admin.telegram_id}",
        changed_at=utcnow(),
        notes=req.notes or "Ручное изменение курса в админке"
    )
    db.add(audit)

    st.exchange_rate = new_val
    st.exchange_rate_updated_at = utcnow()
    st.exchange_rate_updated_by = admin.username or "Администратор"

    await db.commit()
    await db.refresh(st)
    return st

@router.put("/shipping", response_model=StoreSettingsOut)
async def update_shipping_settings(
    req: ShippingSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")

    st.shipping_rub_per_kg = req.shipping_rub_per_kg
    st.shipping_min_weight_kg = req.shipping_min_weight_kg
    st.updated_at = utcnow()

    await db.commit()
    await db.refresh(st)
    return st

@router.put("/commission", response_model=StoreSettingsOut)
async def update_commission_settings(
    req: CommissionSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")

    st.commission_type = req.commission_type
    st.commission_value = req.commission_value
    if req.commission_fixed_bonus is not None:
        st.commission_fixed_bonus = req.commission_fixed_bonus
    st.updated_at = utcnow()

    await db.commit()
    await db.refresh(st)
    return st

@router.put("/russia-shipping", response_model=StoreSettingsOut)
async def update_russia_shipping(
    req: RussiaShippingSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")

    st.russia_shipping_type = req.russia_shipping_type
    st.russia_shipping_cost = req.russia_shipping_cost
    st.updated_at = utcnow()

    await db.commit()
    await db.refresh(st)
    return st

@router.put("/payment", response_model=StoreSettingsOut)
async def update_payment_settings(
    req: PaymentSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(StoreSettings))
    st = res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Настройки не найдены")

    st.payment_bank_name = req.payment_bank_name
    st.payment_phone = req.payment_phone
    st.payment_card_number = req.payment_card_number
    st.payment_recipient_name = req.payment_recipient_name
    st.payment_instructions = req.payment_instructions
    if req.support_telegram_username is not None:
        st.support_telegram_username = req.support_telegram_username
    st.payment_is_configured = bool(req.payment_is_configured and req.payment_bank_name.strip()
                                     and req.payment_recipient_name.strip()
                                     and (req.payment_phone.strip() or req.payment_card_number.strip()))
    st.updated_at = utcnow()

    await db.commit()
    await db.refresh(st)
    return st
