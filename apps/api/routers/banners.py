from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.database import get_db
from apps.api.models import Banner, User
from apps.api.schemas import BannerOut
from apps.api.security import get_current_admin

router = APIRouter(prefix="/banners", tags=["banners"])

class BannerCreate(BaseModel):
    title: str
    subtitle: Optional[str] = None
    badge_text: Optional[str] = None
    image_url: str
    link_url: Optional[str] = "/catalog"
    is_active: bool = True
    order_index: int = 1

@router.get("", response_model=List[BannerOut])
async def list_banners(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Banner)
        .where(Banner.is_active == True)
        .order_by(Banner.order_index.asc(), Banner.id.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=BannerOut)
async def create_banner(
    data: BannerCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    banner = Banner(
        title=data.title,
        subtitle=data.subtitle,
        badge_text=data.badge_text,
        image_url=data.image_url,
        link_url=data.link_url,
        is_active=data.is_active,
        order_index=data.order_index
    )
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return banner

@router.put("/{banner_id}", response_model=BannerOut)
async def update_banner(
    banner_id: int,
    data: BannerCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Banner).where(Banner.id == banner_id)
    res = await db.execute(stmt)
    banner = res.scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Баннер не найден")

    banner.title = data.title
    banner.subtitle = data.subtitle
    banner.badge_text = data.badge_text
    banner.image_url = data.image_url
    banner.link_url = data.link_url
    banner.is_active = data.is_active
    banner.order_index = data.order_index

    await db.commit()
    await db.refresh(banner)
    return banner

@router.delete("/{banner_id}")
async def delete_banner(
    banner_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Banner).where(Banner.id == banner_id)
    res = await db.execute(stmt)
    banner = res.scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Баннер не найден")

    await db.delete(banner)
    await db.commit()
    return {"status": "ok", "deleted_id": banner_id}
