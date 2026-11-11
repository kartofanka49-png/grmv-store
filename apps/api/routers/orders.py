import io
import uuid
import datetime
from decimal import Decimal
from pathlib import Path
from PIL import Image, ImageOps
from fastapi.responses import FileResponse
from typing import List, Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.models import (
    Order, OrderItem, PaymentProof, OrderStatusHistory,
    CartItem, Product, StoreSettings, User, PromoCode, OrderDeletionWatermark
)
from apps.api.schemas import CartOrderRequest, CartQuoteRequest, OrderOut, OrderCreateRequest, PaymentProofOut
from apps.api.security import get_current_user
from apps.api.pricing import PriceBreakdown, PricingEngine, round_money
from apps.api.config import settings
from apps.bot.notifier import notify_admins_new_order, notify_admins_receipt_uploaded

router = APIRouter(prefix="/orders", tags=["orders"])

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

@router.get("/me", response_model=List[OrderOut])
async def get_my_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
        .order_by(Order.id.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{order_id}", response_model=OrderOut)
async def get_order_by_id(
    order_id: int,
    current_user: User = Depends(get_current_user),
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")
    
    # Ownership or admin check
    is_admin = (current_user.role == "admin" or current_user.telegram_id in settings.admin_id_list)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к чужому заказу")

    return order

@router.post("", response_model=OrderOut)
async def create_order(
    req: OrderCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if req.product_id is None and not settings.DEV_AUTH_ENABLED:
        raise HTTPException(422, "Отправьте ссылку на товар для расчёта администратором.")
    return await save_order(req, background_tasks, current_user, db)


async def store_for_checkout(db, *, require_payment=False):
    store = (await db.execute(select(StoreSettings))).scalar_one_or_none()
    if not store:
        raise HTTPException(500, "Настройки магазина не найдены")
    if store.exchange_rate <= 0:
        raise HTTPException(409, "Магазин ещё настраивает курс юаня.")
    if require_payment and not store.payment_is_configured:
        raise HTTPException(409, "Магазин ещё настраивает оплату.")
    return store


def price_order(store, items, weight, city):
    return PricingEngine.calculate(
        cny_price=sum(item.cny_price * item.quantity for item in items),
        exchange_rate=store.exchange_rate,
        weight_kg=weight,
        shipping_rub_per_kg=store.shipping_rub_per_kg,
        shipping_min_weight_kg=store.shipping_min_weight_kg,
        commission_type=store.commission_type,
        commission_value=store.commission_value,
        commission_fixed_bonus=store.commission_fixed_bonus or Decimal("0.00"),
        russia_shipping_type=store.russia_shipping_type,
        russia_shipping_cost=store.russia_shipping_cost,
        delivery_city=city or "Москва",
    )


def catalog_line(product, size, variant_id, color, quantity, *, from_cart=False):
    if not product or not product.is_active:
        raise HTTPException(409 if from_cart else 404, "Товар больше недоступен.")
    if product.is_demo and not settings.DEV_AUTH_ENABLED:
        raise HTTPException(409, "Демонстрационная карточка. Можно оформить выкуп по ссылке.")
    variant = None
    if variant_id or from_cart:
        variant = next((item for item in product.variants if item.size == size and
                        (item.id == variant_id if variant_id else (item.color or "Default") == (color or "Default"))), None)
    if variant_id or (from_cart and product.variants):
        if not variant or variant.stock_status == "out_of_stock":
            raise HTTPException(409, f"Размер {size} товара «{product.title}» больше недоступен.")
    return OrderItem(
        product_id=product.id, title=product.title, brand=product.brand, category=product.category,
        size=size, color=variant.color if variant else color or "Default", quantity=quantity,
        cny_price=variant.cny_price if variant else product.base_cny_price, image_url=product.image_url,
    )


async def load_cart_selection(req, db, user_id, *, lock=False):
    quantities = {item.id: item.quantity for item in req.items}
    if len(quantities) != len(req.items):
        raise HTTPException(422, "Выберите каждую позицию корзины один раз.")
    selected = (CartItem.user_id == user_id, CartItem.id.in_(quantities))
    if lock:
        # Take write locks before loading the rows, including on SQLite.
        await db.execute(update(CartItem).where(*selected).values(quantity=CartItem.quantity))
    rows = (await db.scalars(select(CartItem).where(*selected)
                            .options(selectinload(CartItem.product).selectinload(Product.variants))
                            .order_by(CartItem.id))).all()
    if len(rows) != len(quantities) or any(row.quantity != quantities[row.id] for row in rows):
        raise HTTPException(409, "Корзина изменилась. Вернитесь в корзину и проверьте выбранные товары.")
    items = [catalog_line(row.product, row.size, row.variant_id, row.color, row.quantity, from_cart=True) for row in rows]
    weight = sum(row.product.estimated_weight_kg * row.quantity for row in rows)
    return rows, items, weight


@router.post("/cart/quote", response_model=PriceBreakdown)
async def quote_cart(req: CartQuoteRequest, current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    store = await store_for_checkout(db)
    _, items, weight = await load_cart_selection(req, db, current_user.id)
    return price_order(store, items, weight, req.delivery_city)


@router.post("/cart", response_model=OrderOut)
async def order_cart(req: CartOrderRequest, background_tasks: BackgroundTasks,
                     current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows, items, weight = await load_cart_selection(req, db, current_user.id, lock=True)
    store = await store_for_checkout(db, require_payment=True)
    for row in rows:
        await db.delete(row)
    return await persist_order(req, background_tasks, current_user, db, store, items, weight)


async def save_order(req, background_tasks, current_user, db, *, initial_status="new", commit=True):
    store = await store_for_checkout(db, require_payment=(
        not settings.DEV_AUTH_ENABLED and initial_status == "new" and bool(req.product_id)
    ))
    if req.product_id:
        product = await db.get(Product, req.product_id, options=(selectinload(Product.variants),))
        item = catalog_line(product, req.size, req.variant_id, req.color, req.quantity)
        item.product_link = req.custom_product_link
        unit_weight = product.estimated_weight_kg
    else:
        if not req.cny_price or req.cny_price <= 0:
            raise HTTPException(400, "Укажите цену товара в юанях (CNY)")
        item = OrderItem(
            title=req.custom_product_title or "Товар по ссылке POIZON",
            brand="", category="Обувь", size=req.size, color=req.color or "Default",
            quantity=req.quantity, cny_price=req.cny_price, image_url="", product_link=req.custom_product_link,
        )
        unit_weight = req.weight_kg or Decimal("1.20")
    return await persist_order(req, background_tasks, current_user, db, store, [item],
                               unit_weight * req.quantity, initial_status=initial_status, commit=commit)


async def persist_order(req, background_tasks, current_user, db, st, items, weight, *, initial_status="new", commit=True):
    breakdown = price_order(st, items, weight, req.delivery_city)
    # 4. Check & Apply Promo Code if provided
    applied_promo = None
    discount_rub = Decimal("0.00")
    if req.promo_code:
        p_res = await db.execute(
            select(PromoCode).where(
                func.upper(PromoCode.code) == req.promo_code.strip().upper(),
                PromoCode.is_active == True
            )
        )
        promo = p_res.scalar_one_or_none()
        if promo and breakdown.grand_total_rub >= promo.min_order_rub and (
            not promo.usage_limit or promo.used_count < promo.usage_limit
        ):
            if promo.discount_type == "percent":
                discount_rub = (breakdown.grand_total_rub * (promo.discount_value / Decimal("100.00"))).quantize(Decimal("1.00"))
            else:
                discount_rub = min(promo.discount_value, breakdown.grand_total_rub)
            applied_promo = promo.code
            promo.used_count += 1

    if req.expected_total_rub is not None:
        if not st.payment_is_configured:
            raise HTTPException(status_code=409, detail="Оплата ещё не настроена.")
        if req.expected_total_rub != max(Decimal("0.00"), breakdown.grand_total_rub - discount_rub):
            raise HTTPException(status_code=409, detail="Стоимость изменилась. Обновите расчёт перед оформлением.")

    # 5. Generate next order number e.g. #4588
    order_num = "tmp-" + uuid.uuid4().hex[:20]
    status_label = "Ожидает оплаты" if initial_status == "awaiting_payment" else "Новый"

    # 6. Create Order with Immutable Financial Snapshot
    order = Order(
        order_number=order_num,
        user_id=current_user.id,
        status=initial_status,
        status_label_ru=status_label,
        delivery_city=breakdown.delivery_city,
        delivery_address=req.delivery_address,
        customer_name=req.customer_name or current_user.first_name or "Покупатель",
        customer_phone=req.customer_phone or current_user.phone,
        customer_telegram=req.customer_telegram or (f"@{current_user.username}" if current_user.username else None),
        customer_notes=req.customer_notes,
        item_cny_price=breakdown.cny_price,
        exchange_rate_snapshot=st.exchange_rate,
        item_rub_price=breakdown.item_rub_price,
        estimated_weight_kg=weight,
        chargeable_weight_kg=breakdown.chargeable_weight_kg,
        intl_delivery_rate_rub=st.shipping_rub_per_kg,
        intl_delivery_cost_rub=breakdown.intl_delivery_cost_rub,
        russia_delivery_cost_rub=breakdown.russia_shipping_cost_rub,
        is_russia_delivery_known=breakdown.is_russia_delivery_known,
        commission_cost_rub=breakdown.commission_cost_rub,
        commission_description=breakdown.commission_label_ru,
        buyout_total_rub=max(Decimal("0.00"), breakdown.buyout_total_rub - discount_rub),
        grand_total_rub=max(Decimal("0.00"), breakdown.grand_total_rub - discount_rub),
        paid_amount_rub=Decimal("0.00"),
        is_buyout_paid=False,
        is_fully_paid=False,
        promo_code=applied_promo,
        promo_discount_rub=discount_rub
    )
    db.add(order)
    await db.flush()

    if db.bind.dialect.name == "sqlite":
        watermark = await db.get(OrderDeletionWatermark, 1)
        if watermark and order.id <= watermark.last_deleted_id:
            # SQLite can reuse the largest rowid after it has been deleted.
            order.id = watermark.last_deleted_id + 1
    order.order_number = f"#{4587 + order.id}"

    # Use cumulative rounding so line totals always add up to the order subtotal.
    cumulative_cny = Decimal("0.00")
    cumulative_rub = Decimal("0.00")
    for item in items:
        cumulative_cny += item.cny_price * item.quantity
        subtotal = round_money(cumulative_cny * st.exchange_rate)
        item.rub_price = subtotal - cumulative_rub
        cumulative_rub = subtotal
        item.order_id = order.id
    db.add_all(items)

    # 7. Add History
    hist = OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status=initial_status,
        comment="Стоимость согласована администратором" if initial_status == "awaiting_payment" else "Заявка создана",
        changed_by=current_user.username or "Покупатель"
    )
    db.add(hist)

    if commit:
        await db.commit()
    else:
        await db.flush()

    # Trigger admin notification in background
    items_desc = "\n".join(f"• {item.title} (Размер: {item.size}) — {item.quantity} шт." for item in items[:8])
    if len(items) > 8:
        items_desc += f"\nЕщё позиций: {len(items) - 8}. Полный список в заказе."
    background_tasks.add_task(
        notify_admins_new_order,
        order.order_number,
        order.customer_name,
        order.customer_telegram,
        str(int(order.grand_total_rub)),
        str(int(order.item_cny_price)),
        items_desc,
        order.delivery_city or "Москва"
    )

    # Reload with relationships
    stmt = (
        select(Order)
        .where(Order.id == order.id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment_proofs),
            selectinload(Order.status_history)
        )
    )
    res = await db.execute(stmt)
    return res.scalar_one()

@router.get("/receipts/{filename}")
async def read_receipt(filename: str, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(Order).join(PaymentProof, PaymentProof.order_id == Order.id)
        .where(PaymentProof.receipt_image_url == f"/uploads/receipts/{filename}"))).scalars().first()
    if not order or (order.user_id != current_user.id and current_user.telegram_id not in settings.admin_id_list):
        raise HTTPException(404, "Чек не найден.")
    path = Path(settings.UPLOAD_DIR) / "receipts" / filename
    if not path.is_file():
        raise HTTPException(404, "Файл чека не найден.")
    return FileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{order_id}/payment-proof", response_model=PaymentProofOut)
async def upload_payment_proof(
    order_id: int,
    background_tasks: BackgroundTasks,
    receipt_file: UploadFile = File(...),
    amount: Annotated[Optional[str], Form()] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.payment_proofs),
            selectinload(Order.items)
        )
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # Only order owner or admin can upload
    is_admin = (current_user.role == "admin" or current_user.telegram_id in settings.admin_id_list)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заказу")

    allowed_statuses = ("new", "awaiting_payment")
    previous_status = order.status
    if previous_status not in allowed_statuses:
        raise HTTPException(409, "На этом этапе чек не требуется.")
    filename = Path(receipt_file.filename or "receipt.jpg").name[:180]
    limit = 10 * 1024 * 1024
    contents = await receipt_file.read(limit + 1)
    if len(contents) > limit:
        raise HTTPException(413, "Размер чека не должен превышать 10 МБ.")
    try:
        with Image.open(io.BytesIO(contents), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError
            converted = ImageOps.exif_transpose(image).convert("RGB")
            converted.thumbnail((2000, 2000))
            output = io.BytesIO()
            converted.save(output, format="WEBP", quality=88)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "Загрузите читаемый чек в формате PNG, JPG или WebP.") from None

    claimed = await db.execute(update(Order).where(Order.id == order.id, Order.status.in_(allowed_statuses))
        .values(status="payment_review", status_label_ru="Проверка оплаты"))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Статус заказа изменился. Обновите страницу.")

    receipts = Path(settings.UPLOAD_DIR) / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    saved_filename = f"receipt_{order.id}_{uuid.uuid4().hex}.webp"
    saved_path = str(receipts / saved_filename)
    with open(saved_path, "wb") as f:
        f.write(output.getvalue())
    receipt_url = f"/uploads/receipts/{saved_filename}"

    # Create PaymentProof
    proof_amount = order.grand_total_rub
    proof = PaymentProof(
        order_id=order.id,
        user_id=current_user.id,
        amount_rub=proof_amount,
        payment_type="buyout",
        receipt_filename=filename,
        receipt_image_url=receipt_url,
        status="submitted"
    )
    db.add(proof)

    # Update order status to payment_review
    order.status = "payment_review"
    order.status_label_ru = "Проверка оплаты"

    hist = OrderStatusHistory(
        order_id=order.id,
        from_status=previous_status,
        to_status="payment_review",
        comment=f"Чек загружен ({filename}), ожидает подтверждения администратором",
        changed_by=current_user.username or "Покупатель"
    )
    db.add(hist)

    await db.commit()

    # Trigger admin notification with receipt photo and details in background
    items_desc = "\n".join([f"• {it.title} (Размер: {it.size}) — {it.quantity} шт." for it in order.items]) if order.items else "Товары из заказа"
    background_tasks.add_task(
        notify_admins_receipt_uploaded,
        order.order_number,
        order.id,
        order.customer_name,
        order.customer_telegram,
        str(int(order.grand_total_rub)),
        str(int(order.item_cny_price)),
        items_desc,
        order.delivery_city or "Москва",
        saved_path
    )
    await db.refresh(proof)
    return proof
