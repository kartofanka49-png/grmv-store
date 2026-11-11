from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from apps.api.database import get_db
from apps.api.models import PromoCode, User
from apps.api.schemas import (
    PromoCodeOut, PromoCodeCreate,
    PromoCodeValidateRequest, PromoCodeValidateResponse
)
from apps.api.security import get_current_user, get_current_admin

router = APIRouter(prefix="/promocodes", tags=["promocodes"])

@router.post("/validate", response_model=PromoCodeValidateResponse)
async def validate_promocode(
    req: PromoCodeValidateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    code_clean = req.code.strip().upper()
    stmt = select(PromoCode).where(
        func.upper(PromoCode.code) == code_clean,
        PromoCode.is_active == True
    )
    res = await db.execute(stmt)
    promo = res.scalar_one_or_none()

    if not promo:
        raise HTTPException(status_code=400, detail="Промокод не существует или не активен")

    if promo.usage_limit and promo.used_count >= promo.usage_limit:
        raise HTTPException(status_code=400, detail="Лимит использований промокода исчерпан")

    if req.order_total_rub < promo.min_order_rub:
        raise HTTPException(
            status_code=400,
            detail=f"Промокод действует для заказов от {promo.min_order_rub:,.0f} ₽".replace(",", " ")
        )

    # Calculate discount
    if promo.discount_type == "percent":
        discount = (req.order_total_rub * (promo.discount_value / Decimal("100.00"))).quantize(Decimal("1.00"))
    else:
        discount = min(promo.discount_value, req.order_total_rub)

    final_total = max(Decimal("0.00"), req.order_total_rub - discount)

    return PromoCodeValidateResponse(
        valid=True,
        code=promo.code,
        discount_rub=discount,
        message=promo.description or f"Скидка {discount:,.0f} ₽ применена".replace(",", " "),
        final_total_rub=final_total
    )

@router.get("", response_model=List[PromoCodeOut])
async def list_promocodes(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PromoCode).order_by(PromoCode.id.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=PromoCodeOut)
async def create_promocode(
    data: PromoCodeCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    code_clean = data.code.strip().upper()
    existing = await db.execute(select(PromoCode).where(func.upper(PromoCode.code) == code_clean))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Промокод {code_clean} уже существует")

    promo = PromoCode(
        code=code_clean,
        description=data.description,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        min_order_rub=data.min_order_rub,
        is_active=data.is_active
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return promo

@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promocode(
    promo_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    promo = await db.get(PromoCode, promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    await db.delete(promo)
    await db.commit()
