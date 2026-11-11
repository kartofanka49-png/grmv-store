from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.config import settings
from apps.api.models import CartItem, Product, ProductVariant, User
from apps.api.schemas import CartItemAdd, CartItemOut
from apps.api.security import get_current_user

router = APIRouter(prefix="/cart", tags=["cart"])

@router.get("", response_model=List[CartItemOut])
async def get_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(CartItem)
        .join(Product)
        .where(CartItem.user_id == current_user.id)
        .options(
            selectinload(CartItem.product).selectinload(Product.variants)
        )
        .order_by(CartItem.id.asc())
    )
    if not settings.DEV_AUTH_ENABLED:
        stmt = stmt.where(Product.is_demo.is_(False))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=CartItemOut)
async def add_to_cart(
    item_in: CartItemAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Serialize additions for the same buyer, including the first addition of a variant.
    await db.execute(update(User).where(User.id == current_user.id).values(updated_at=User.updated_at))
    product = await db.get(Product, item_in.product_id, options=(selectinload(Product.variants),))
    if not product or not product.is_active or (product.is_demo and not settings.DEV_AUTH_ENABLED):
        raise HTTPException(404, "Товар больше недоступен.")
    variant = next((item for item in product.variants if item.id == item_in.variant_id and item.size == item_in.size), None)
    if item_in.variant_id and (not variant or variant.stock_status == "out_of_stock"):
        raise HTTPException(409, "Выбранный размер больше недоступен.")
    # Keep variants with the same size but different colors separate.
    stmt = select(CartItem).where(
        CartItem.user_id == current_user.id,
        CartItem.product_id == item_in.product_id,
        CartItem.size == item_in.size,
        CartItem.variant_id == item_in.variant_id,
    )
    existing = (await db.scalars(stmt.order_by(CartItem.id))).first()

    if existing:
        if existing.quantity + item_in.quantity > 10:
            raise HTTPException(409, "В корзине уже максимальное количество для этой позиции — 10 шт.")
        existing.quantity += item_in.quantity
        await db.commit()
        await db.refresh(existing)
        target_id = existing.id
    else:
        new_item = CartItem(
            user_id=current_user.id,
            product_id=item_in.product_id,
            variant_id=item_in.variant_id,
            size=item_in.size,
            color=(variant.color or "Default") if variant else item_in.color,
            quantity=item_in.quantity
        )
        db.add(new_item)
        await db.commit()
        await db.refresh(new_item)
        target_id = new_item.id

    # Fetch loaded
    stmt = (
        select(CartItem)
        .where(CartItem.id == target_id)
        .options(selectinload(CartItem.product).selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    return res.scalar_one()

@router.put("/{item_id}", response_model=CartItemOut)
async def update_cart_item(
    item_id: int,
    quantity: int = Query(le=10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CartItem).join(Product).where(CartItem.id == item_id, CartItem.user_id == current_user.id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Позиция корзины не найдена")

    if quantity <= 0:
        await db.delete(item)
        await db.commit()
        return Response(status_code=204)

    item.quantity = quantity
    await db.commit()

    stmt = (
        select(CartItem)
        .where(CartItem.id == item_id)
        .options(selectinload(CartItem.product).selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    return res.scalar_one()

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_cart(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CartItem).where(CartItem.id == item_id, CartItem.user_id == current_user.id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()
    return None

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CartItem).where(CartItem.user_id == current_user.id)
    res = await db.execute(stmt)
    for it in res.scalars().all():
        await db.delete(it)
    await db.commit()
    return None
