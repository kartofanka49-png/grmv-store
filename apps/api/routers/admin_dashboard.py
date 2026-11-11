from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from apps.api.database import get_db
from apps.api.models import Order, StoreSettings, User
from apps.api.schemas import AdminDashboardOut
from apps.api.security import get_current_admin

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

@router.get("", response_model=AdminDashboardOut)
async def get_dashboard_metrics(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # Total count and sum
    total_orders_res = await db.execute(select(func.count(Order.id)))
    total_orders = total_orders_res.scalar() or 0

    total_rev_res = await db.execute(select(func.sum(Order.grand_total_rub)))
    total_rev = total_rev_res.scalar() or Decimal("0.00")

    # In progress statuses: new, awaiting_quote_confirmation, awaiting_payment, payment_review, paid, purchased, china_warehouse, shipped
    in_progress_res = await db.execute(
        select(func.count(Order.id)).where(
            Order.status.in_([
                "new", "awaiting_quote_confirmation", "awaiting_payment",
                "payment_review", "paid", "purchased", "china_warehouse", "shipped"
            ])
        )
    )
    in_progress = in_progress_res.scalar() or 0

    # Delivered count
    delivered_res = await db.execute(
        select(func.count(Order.id)).where(Order.status == "delivered")
    )
    delivered = delivered_res.scalar() or 0

    # New count
    new_res = await db.execute(select(func.count(Order.id)).where(Order.status == "new"))
    new_count = new_res.scalar() or 0

    # Awaiting payment
    awaiting_pay_res = await db.execute(
        select(func.count(Order.id)).where(Order.status.in_(["awaiting_payment", "payment_review"]))
    )
    awaiting_pay = awaiting_pay_res.scalar() or 0

    # Settings
    st_res = await db.execute(select(StoreSettings))
    st = st_res.scalar_one_or_none()

    return AdminDashboardOut(
        total_orders=total_orders,
        total_revenue_rub=total_rev,
        in_progress_count=in_progress,
        delivered_count=delivered,
        current_exchange_rate=st.exchange_rate if st else Decimal("12.80"),
        shipping_rate_per_kg=st.shipping_rub_per_kg if st else Decimal("680.00"),
        new_orders_count=new_count,
        awaiting_payment_count=awaiting_pay
    )
