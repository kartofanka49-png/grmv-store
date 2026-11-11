import datetime
import logging
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc, update
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.models import Order, OrderItem, PaymentProof, OrderStatusHistory, User, OrderDeletionWatermark
from apps.api.config import settings
from apps.api.schemas import OrderCreateRequest, OrderOut
from apps.api.routers.orders import save_order
from apps.api.security import get_current_admin
from apps.bot.notifier import notify_buyer_payment_approved, notify_buyer_status_update

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])
logger = logging.getLogger(__name__)

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

STATUS_RU_MAP = {
    "new": "Новый",
    "awaiting_quote_confirmation": "Согласование стоимости",
    "awaiting_payment": "Ожидает оплаты",
    "payment_review": "Проверка оплаты",
    "paid": "Оплачен",
    "purchased": "Выкуплен",
    "china_warehouse": "На складе в Китае",
    "shipped": "Отправлен",
    "delivered": "Доставлен",
    "cancelled": "Отменён"
}

class StatusUpdateRequest(BaseModel):
    status: str
    comment: Optional[str] = None

class WeightTrackingUpdateRequest(BaseModel):
    actual_weight_kg: Optional[Decimal] = Field(None, gt=0, le=1000)
    tracking_number: Optional[str] = Field(None, max_length=100)
    shipping_carrier: Optional[str] = Field(None, max_length=100)
    tracking_url: Optional[HttpUrl] = None

class ConfirmPaymentRequest(BaseModel):
    proof_id: Optional[int] = None
    admin_comment: Optional[str] = "Оплата подтверждена администратором"

class RejectPaymentRequest(BaseModel):
    proof_id: Optional[int] = None
    reason: str = "Чек не прошёл проверку"

class ManualOrderInput(OrderCreateRequest):
    telegram_id: int = 0


@router.post("/manual", response_model=OrderOut)
async def manual_order(data: ManualOrderInput, background_tasks: BackgroundTasks,
                       admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    buyer = admin
    if data.telegram_id:
        buyer = (await db.execute(select(User).where(User.telegram_id == data.telegram_id))).scalar_one_or_none()
        if not buyer:
            raise HTTPException(404, "Покупатель должен сначала открыть Mini App.")
    return await save_order(data, background_tasks, buyer, db)


@router.get("", response_model=List[OrderOut])
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )

    if status_filter and status_filter != "all" and status_filter != "Все заказы":
        ru_to_code = {v: k for k, v in STATUS_RU_MAP.items()}
        code = ru_to_code.get(status_filter, status_filter)
        if code == "Новые": code = "new"
        elif code == "Ожидает оплаты": code = "awaiting_payment"
        elif code == "Оплачен": code = "paid"
        elif code == "Выкуплен": code = "purchased"
        elif code == "На складе в Китае": code = "china_warehouse"
        elif code in ["Отправлен", "В пути"]: code = "shipped"
        elif code == "Доставлен": code = "delivered"
        elif code == "Отменён": code = "cancelled"
        
        stmt = stmt.where(Order.status == code)

    if search:
        search_fmt = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Order.order_number.ilike(search_fmt),
                Order.customer_name.ilike(search_fmt),
                Order.customer_telegram.ilike(search_fmt),
                Order.customer_phone.ilike(search_fmt),
                Order.tracking_number.ilike(search_fmt),
                Order.items.any(OrderItem.title.ilike(search_fmt)),
            )
        )

    stmt = stmt.order_by(desc(Order.id))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{order_id}", response_model=OrderOut)
async def get_order_details(
    order_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order

@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: int, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    # Serialize with receipt uploads before reading the files attached to this order.
    locked = await db.execute(update(Order).where(Order.id == order_id)
                              .values(updated_at=Order.updated_at).returning(Order.id))
    if locked.scalar_one_or_none() is None:
        return

    order = await db.get(Order, order_id, options=(selectinload(Order.items), selectinload(Order.payment_proofs),
                                                   selectinload(Order.status_history)))
    receipts = []
    for proof in order.payment_proofs:
        prefix = "/uploads/receipts/"
        filename = proof.receipt_image_url.removeprefix(prefix)
        if proof.receipt_image_url.startswith(prefix) and filename not in {"", ".", ".."} and Path(filename).name == filename:
            receipts.append(Path(settings.UPLOAD_DIR) / "receipts" / filename)

    if db.bind.dialect.name == "sqlite":
        watermark = await db.get(OrderDeletionWatermark, 1)
        if watermark is None:
            db.add(OrderDeletionWatermark(id=1, last_deleted_id=order_id))
        else:
            watermark.last_deleted_id = max(watermark.last_deleted_id, order_id)

    await db.delete(order)
    await db.commit()
    for path in receipts:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove receipt file for deleted order %s", order_id)


@router.post("/{order_id}/confirm-payment", response_model=OrderOut)
async def confirm_payment(
    order_id: int,
    req: ConfirmPaymentRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # Mark proof approved
    if order.payment_proofs:
        target_proof = None
        if req.proof_id:
            for p in order.payment_proofs:
                if p.id == req.proof_id:
                    target_proof = p
                    break
        else:
            target_proof = order.payment_proofs[-1]
        
        if target_proof:
            target_proof.status = "approved"
            target_proof.admin_comment = req.admin_comment
            target_proof.reviewed_at = utcnow()
            target_proof.reviewed_by = admin.username or "Администратор"

    # Update order financial status
    order.is_buyout_paid = True
    order.paid_amount_rub = order.grand_total_rub
    old_status = order.status
    order.status = "paid"
    order.status_label_ru = STATUS_RU_MAP.get("paid", "Оплачен")
    order.updated_at = utcnow()

    # Add audit status history
    hist = OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status="paid",
        comment=req.admin_comment or "Поступление денежных средств подтверждено администратором",
        changed_by=admin.username or "Администратор"
    )
    db.add(hist)

    await db.commit()
    await db.refresh(order)

    # Notify buyer in background
    user_res = await db.execute(select(User).where(User.id == order.user_id))
    buyer = user_res.scalar_one_or_none()
    if buyer and buyer.telegram_id:
        background_tasks.add_task(
            notify_buyer_payment_approved,
            buyer.telegram_id,
            order.order_number
        )

    return order

@router.post("/{order_id}/reject-payment", response_model=OrderOut)
async def reject_payment(
    order_id: int,
    req: RejectPaymentRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    if order.payment_proofs:
        target_proof = order.payment_proofs[-1]
        target_proof.status = "rejected"
        target_proof.admin_comment = req.reason
        target_proof.reviewed_at = utcnow()
        target_proof.reviewed_by = admin.username or "Администратор"

    old_status = order.status
    order.status = "awaiting_payment"
    order.status_label_ru = STATUS_RU_MAP.get("awaiting_payment", "Ожидает оплаты")
    order.updated_at = utcnow()

    hist = OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status="awaiting_payment",
        comment=f"Оплата отклонена: {req.reason}",
        changed_by=admin.username or "Администратор"
    )
    db.add(hist)

    await db.commit()
    await db.refresh(order)
    return order

@router.post("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    req: StatusUpdateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    new_st = req.status
    if new_st not in STATUS_RU_MAP:
        raise HTTPException(status_code=400, detail=f"Недопустимый статус: {new_st}")

    old_st = order.status
    order.status = new_st
    order.status_label_ru = STATUS_RU_MAP[new_st]
    order.updated_at = utcnow()

    if new_st == "shipped" and not order.shipped_at:
        order.shipped_at = utcnow()

    hist = OrderStatusHistory(
        order_id=order.id,
        from_status=old_st,
        to_status=new_st,
        comment=req.comment or f"Статус изменён на «{STATUS_RU_MAP[new_st]}»",
        changed_by=admin.username or "Администратор"
    )
    db.add(hist)

    await db.commit()
    await db.refresh(order)

    # Notify buyer in background
    user_res = await db.execute(select(User).where(User.id == order.user_id))
    buyer = user_res.scalar_one_or_none()
    if buyer and buyer.telegram_id:
        background_tasks.add_task(
            notify_buyer_status_update,
            buyer.telegram_id,
            order.order_number,
            STATUS_RU_MAP[new_st],
            req.comment
        )

    return order

@router.put("/{order_id}/weight-tracking", response_model=OrderOut)
async def update_weight_and_tracking(
    order_id: int,
    req: WeightTrackingUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    if req.actual_weight_kg is not None:
        order.actual_weight_kg = req.actual_weight_kg
        order.chargeable_weight_kg = max(req.actual_weight_kg, Decimal("0.30"))
        order.intl_delivery_cost_rub = round(order.chargeable_weight_kg * order.intl_delivery_rate_rub, 2)
        order.grand_total_rub = max(Decimal("0.00"),
            order.item_rub_price +
            order.intl_delivery_cost_rub +
            order.commission_cost_rub +
            (order.russia_delivery_cost_rub if order.is_russia_delivery_known else Decimal("0.00")) -
            order.promo_discount_rub
        )

    if req.tracking_number is not None:
        order.tracking_number = req.tracking_number.strip() or None

    if req.shipping_carrier is not None:
        order.shipping_carrier = req.shipping_carrier.strip() or None

    if "tracking_url" in req.model_fields_set:
        url = str(req.tracking_url) if req.tracking_url else None
        if url and (len(url) > 500 or req.tracking_url.username or req.tracking_url.password):
            raise HTTPException(422, "Укажите публичную ссылку перевозчика длиной до 500 символов.")
        order.tracking_url = url

    order.updated_at = utcnow()
    await db.commit()
    await db.refresh(order)
    return order
