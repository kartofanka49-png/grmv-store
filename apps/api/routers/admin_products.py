import io
from pathlib import Path
from PIL import Image, ImageOps
from apps.api.config import settings
import uuid
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from apps.api.database import get_db
from apps.api.models import Product, ProductVariant, User
from apps.api.schemas import ProductOut, ProductCreate
from apps.api.security import get_current_admin

router = APIRouter(prefix="/admin/products", tags=["admin-products"])

@router.get("", response_model=List[ProductOut])
async def admin_list_products(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Product)
        .options(selectinload(Product.variants))
        .order_by(Product.id.desc())
    )
    if not settings.DEV_AUTH_ENABLED:
        stmt = stmt.where(Product.is_demo.is_(False))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=ProductOut)
async def admin_create_product(
    prod_in: ProductCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    prod = Product(
        title=prod_in.title,
        brand=prod_in.brand,
        category=prod_in.category,
        description=prod_in.description,
        source=prod_in.source,
        base_cny_price=prod_in.base_cny_price,
        old_price_rub=prod_in.old_price_rub,
        discount_percent=prod_in.discount_percent,
        estimated_weight_kg=prod_in.estimated_weight_kg,
        image_url=prod_in.image_url,
        badge_text=prod_in.badge_text,
        is_active=prod_in.is_active,
        is_popular=prod_in.is_popular,
        is_demo=settings.DEV_AUTH_ENABLED and bool(prod_in.is_demo)
    )
    db.add(prod)
    await db.flush()

    for v in prod_in.variants:
        var = ProductVariant(
            product_id=prod.id,
            size=v.size,
            color=v.color,
            cny_price=v.cny_price,
            stock_status=v.stock_status
        )
        db.add(var)

    await db.commit()

    stmt = (
        select(Product)
        .where(Product.id == prod.id)
        .options(selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    return res.scalar_one()

class QuickPriceUpdate(BaseModel):
    base_cny_price: Optional[Decimal] = None
    old_price_rub: Optional[Decimal] = None
    discount_percent: Optional[int] = None

class QuickPhotoUpdate(BaseModel):
    image_url: str

@router.patch("/{product_id}/photo", response_model=ProductOut)
async def admin_quick_update_photo(
    product_id: int,
    data: QuickPhotoUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")

    prod.image_url = data.image_url.strip()
    await db.commit()
    await db.refresh(prod)
    return prod

@router.patch("/{product_id}/price", response_model=ProductOut)
async def admin_quick_update_price(
    product_id: int,
    data: QuickPriceUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")

    if data.base_cny_price is not None:
        prod.base_cny_price = data.base_cny_price
        # Update variant cny prices as well
        for v in prod.variants:
            v.cny_price = data.base_cny_price

    if data.old_price_rub is not None:
        prod.old_price_rub = data.old_price_rub

    if data.discount_percent is not None:
        prod.discount_percent = data.discount_percent

    await db.commit()
    await db.refresh(prod)
    return prod

@router.put("/{product_id}", response_model=ProductOut)
async def admin_update_product(
    product_id: int,
    prod_in: ProductCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants))
    )
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")

    prod.title = prod_in.title
    prod.brand = prod_in.brand
    prod.category = prod_in.category
    prod.description = prod_in.description
    prod.source = prod_in.source
    prod.base_cny_price = prod_in.base_cny_price
    prod.old_price_rub = prod_in.old_price_rub
    prod.discount_percent = prod_in.discount_percent
    prod.estimated_weight_kg = prod_in.estimated_weight_kg
    prod.image_url = prod_in.image_url
    prod.badge_text = prod_in.badge_text
    prod.is_active = prod_in.is_active
    prod.is_popular = prod_in.is_popular
    if settings.DEV_AUTH_ENABLED and prod_in.is_demo is not None:
        prod.is_demo = prod_in.is_demo

    # Re-create variants if provided
    if prod_in.variants:
        for old_v in prod.variants:
            await db.delete(old_v)
        await db.flush()

        for v in prod_in.variants:
            var = ProductVariant(
                product_id=prod.id,
                size=v.size,
                color=v.color,
                cny_price=v.cny_price,
                stock_status=v.stock_status
            )
            db.add(var)

    await db.commit()
    await db.refresh(prod)
    return prod

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_product(
    product_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Product).where(Product.id == product_id)
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if prod:
        await db.delete(prod)
        await db.commit()
    return None

@router.post("/upload-photo")
async def upload_product_photo(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin)
):
    limit = 10 * 1024 * 1024
    contents = await file.read(limit + 1)
    if len(contents) > limit:
        raise HTTPException(413, "Фото должно быть не больше 10 МБ.")
    try:
        with Image.open(io.BytesIO(contents), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1600, 1600))
            data = io.BytesIO()
            image.save(data, "WEBP", quality=88)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "Загрузите читаемое фото в JPG, PNG или WebP.") from None
    products = Path(settings.UPLOAD_DIR) / "products"
    products.mkdir(parents=True, exist_ok=True)
    name = f"prod_{uuid.uuid4().hex}.webp"
    (products / name).write_bytes(data.getvalue())
    return {"url": f"/uploads/products/{name}"}
