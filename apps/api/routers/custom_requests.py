from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from apps.api.database import get_db
from apps.api.models import CustomBuyoutRequest, StoreSettings, User
from apps.api.schemas import CustomBuyoutCreate, CustomBuyoutOut, OrderCreateRequest, OrderOut
from apps.api.security import get_current_user, get_current_admin
from apps.bot.notifier import notify_admins_custom_buyout, notify_buyer_status_update
from apps.api.routers.orders import save_order
from pydantic import BaseModel, Field
from urllib.parse import urlsplit

router = APIRouter(prefix="/custom-requests", tags=["custom-requests"])

@router.post("", response_model=CustomBuyoutOut)
async def submit_custom_request(
    data: CustomBuyoutCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not data.link_or_title.strip():
        raise HTTPException(status_code=400, detail="Укажите ссылку на товар или его название")

    name = data.customer_name or current_user.first_name or "Покупатель"
    tg = data.customer_telegram or (f"@{current_user.username}" if current_user.username else None)

    req = CustomBuyoutRequest(
        user_id=current_user.id,
        customer_name=name,
        customer_telegram=tg,
        link_or_title=data.link_or_title.strip(),
        size=data.size.strip() if data.size else None,
        cny_price=data.cny_price,
        image_url=data.image_url.strip() if data.image_url else None,
        notes=data.notes.strip() if data.notes else None,
        status="pending"
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    # Notify admins via Telegram bot
    background_tasks.add_task(
        notify_admins_custom_buyout,
        request_id=req.id,
        customer_name=name,
        customer_telegram=tg,
        link_or_title=req.link_or_title,
        size=req.size,
        cny_price=req.cny_price,
        notes=req.notes
    )

    return req

@router.get("", response_model=List[CustomBuyoutOut])
async def list_custom_requests(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CustomBuyoutRequest).order_by(CustomBuyoutRequest.id.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


class QuoteInput(BaseModel):
    cny_price: Decimal = Field(gt=0, le=1000000, decimal_places=2)
    weight_kg: Decimal = Field(gt=0, le=100)
    city: str = Field(min_length=1, max_length=100)


@router.post("/{request_id}/quote", response_model=OrderOut)
async def quote_request(request_id: int, data: QuoteInput, background_tasks: BackgroundTasks,
                        admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    prefs = (await db.execute(select(StoreSettings))).scalar_one_or_none()
    if not prefs or not prefs.payment_is_configured or prefs.exchange_rate <= 0:
        raise HTTPException(409, "Настройте курс и реквизиты для оплаты.")
    result = await db.execute(update(CustomBuyoutRequest)
        .where(CustomBuyoutRequest.id == request_id, CustomBuyoutRequest.status == "pending")
        .values(status="quoted").returning(CustomBuyoutRequest))
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(409, "Заявка уже обработана или не найдена.")
    buyer = await db.get(User, request.user_id)
    try:
        link = urlsplit(request.link_or_title)
        valid_link = link.scheme in {"http", "https"} and link.hostname and not link.username
    except ValueError:
        valid_link = False
    order = await save_order(OrderCreateRequest(
        custom_product_title="Выкуп по ссылке" if valid_link else request.link_or_title[:255],
        custom_product_link=request.link_or_title if valid_link else None,
        size=request.size or "По заявке", quantity=1, delivery_city=data.city.strip(),
        customer_name=request.customer_name, customer_telegram=request.customer_telegram,
        customer_notes=request.notes, cny_price=data.cny_price, weight_kg=data.weight_kg,
    ), background_tasks, buyer, db, initial_status="awaiting_payment", commit=False)
    await db.commit()
    background_tasks.add_task(notify_buyer_status_update, buyer.telegram_id, order.order_number,
                              "Стоимость согласована. Откройте заказ, чтобы загрузить чек.")
    return order
