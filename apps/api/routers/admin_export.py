import csv
import io
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.models import Order, User
from apps.api.security import get_current_admin

router = APIRouter(prefix="/admin/export", tags=["admin-export"])

@router.get("/orders.csv")
async def export_orders_csv(
    ids: list[int] | None = Query(None),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(desc(Order.id))
    )
    if ids:
        stmt = stmt.where(Order.id.in_(ids))
    res = await db.execute(stmt)
    orders = res.scalars().all()

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Cyrillic properly
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    # Header
    writer.writerow([
        "№ заказа",
        "Статус",
        "Клиент",
        "Telegram",
        "Телефон",
        "Город доставки",
        "Товар",
        "Размер",
        "Кол-во",
        "Цена CNY",
        "Курс юаня",
        "Товар ₽",
        "Вес (кг)",
        "Доставка RaketaCN ₽",
        "Доставка РФ ₽",
        "Комиссия ₽",
        "Итого к оплате ₽",
        "Оплачено ₽",
        "Трек-номер",
        "Дата создания"
    ])

    for o in orders:
        item_title = " | ".join(item.title for item in o.items) or "Товар"
        item_size = " | ".join(item.size for item in o.items)
        item_qty = sum(item.quantity for item in o.items)

        writer.writerow([
            o.order_number,
            o.status_label_ru,
            o.customer_name,
            o.customer_telegram or "",
            o.customer_phone or "",
            o.delivery_city,
            item_title,
            item_size,
            item_qty,
            str(o.item_cny_price),
            str(o.exchange_rate_snapshot),
            str(o.item_rub_price),
            str(o.actual_weight_kg or o.estimated_weight_kg),
            str(o.intl_delivery_cost_rub),
            str(o.russia_delivery_cost_rub),
            str(o.commission_cost_rub),
            str(o.grand_total_rub),
            str(o.paid_amount_rub),
            o.tracking_number or "",
            o.created_at.strftime("%d.%m.%Y %H:%M") if o.created_at else ""
        ])

    csv_data = output.getvalue().encode('utf-8')
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=grmv_orders_export.csv"
        }
    )
