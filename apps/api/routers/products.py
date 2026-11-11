from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.config import settings
from apps.api.models import Product, ProductVariant
from apps.api.schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])

@router.get("", response_model=List[ProductOut])
async def list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    brand: Optional[str] = None,
    is_popular: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Product)
        .where(Product.is_active == True)
        .options(selectinload(Product.variants))
    )
    if not settings.DEV_AUTH_ENABLED:
        stmt = stmt.where(Product.is_demo.is_(False))

    if category and category != "Все":
        stmt = stmt.where(Product.category == category)
    if brand:
        stmt = stmt.where(Product.brand.ilike(f"%{brand}%"))
    if is_popular is not None:
        stmt = stmt.where(Product.is_popular == is_popular)
    if search:
        search_fmt = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.title.ilike(search_fmt),
                Product.brand.ilike(search_fmt),
                Product.description.ilike(search_fmt)
            )
        )

    stmt = stmt.order_by(Product.id.asc())
    res = await db.execute(stmt)
    products = res.scalars().all()
    return products

@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.is_active == True)
        .options(selectinload(Product.variants))
    )
    if not settings.DEV_AUTH_ENABLED:
        stmt = stmt.where(Product.is_demo.is_(False))
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
    return prod
