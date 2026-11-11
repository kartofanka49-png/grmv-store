from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.database import get_db
from apps.api.security import get_current_user, get_or_create_user, verify_telegram_init_data
from apps.api.models import User
from apps.api.schemas import UserOut
from apps.api.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

class TelegramAuthRequest(BaseModel):
    init_data: str

class DevLoginRequest(BaseModel):
    role: str = "buyer"  # "admin" or "buyer"
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None

class AuthResponse(BaseModel):
    user: UserOut
    token: str
    is_admin: bool

@router.post("/telegram", response_model=AuthResponse)
async def auth_telegram(data: TelegramAuthRequest, db: AsyncSession = Depends(get_db)):
    verified = verify_telegram_init_data(data.init_data, settings.BOT_TOKEN)
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверная подпись данных Telegram"
        )

    u_info = verified["user"]
    tg_id = int(u_info["id"])
    user = await get_or_create_user(
        db,
        telegram_id=tg_id,
        username=u_info.get("username"),
        first_name=u_info.get("first_name"),
        last_name=u_info.get("last_name")
    )
    is_admin = (user.telegram_id in settings.admin_id_list)
    return AuthResponse(
        user=user,
        token=f"twa_{user.telegram_id}",
        is_admin=is_admin
    )

@router.post("/dev-login", response_model=AuthResponse)
async def dev_login(data: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    if not settings.DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Режим разработки отключен на этом сервере"
        )
    
    if data.role == "admin":
        tg_id = settings.admin_id_list[0] if settings.admin_id_list else 123456789
        uname = data.username or "admin_luch"
        fname = data.first_name or "Администратор"
    else:
        tg_id = data.telegram_id or 1110001
        uname = data.username or "ivan_p"
        fname = data.first_name or "Иван"

    user = await get_or_create_user(
        db,
        telegram_id=tg_id,
        username=uname,
        first_name=fname,
        last_name="Store" if data.role == "admin" else "П."
    )
    is_admin = (user.telegram_id in settings.admin_id_list)
    return AuthResponse(
        user=user,
        token=f"dev_{user.telegram_id}",
        is_admin=is_admin
    )

@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
