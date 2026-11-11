import hmac
import hashlib
import json
import time
from urllib.parse import parse_qsl, unquote
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.config import settings
from apps.api.database import get_db
from apps.api.models import User

def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256.
    Returns parsed dictionary if valid, None otherwise.
    """
    try:
        if not bot_token:
            return None
        fields = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True, max_num_fields=30)
        parsed_data = dict(fields)
        if len(fields) != len(parsed_data):
            return None
        if "hash" not in parsed_data:
            return None
        
        received_hash = parsed_data.pop("hash")
        
        # Check auth_date for expiration (e.g. 86400 seconds = 24 hours)
        auth_date = int(parsed_data.get("auth_date", 0))
        if not -60 <= time.time() - auth_date <= 43200:
            return None
        
        # Sort keys alphabetically and format as key=value\n
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # secret_key = HMAC_SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        
        # computed_hash = HMAC_SHA256(data_check_string, secret_key)
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(computed_hash, received_hash):
            user_data = json.loads(parsed_data.get("user", "{}"))
            return {
                "user": user_data,
                "auth_date": auth_date,
                "query_id": parsed_data.get("query_id")
            }
        return None
    except Exception:
        return None

async def get_or_create_user(
    db: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> User:
    res = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    
    is_admin = telegram_id in settings.admin_id_list
    role = "admin" if is_admin else "buyer"

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update profile if changed
        updated = False
        if username and user.username != username:
            user.username = username
            updated = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            updated = True
        if user.role != role:
            user.role = role
            updated = True
        if updated:
            await db.commit()
            await db.refresh(user)
            
    return user

async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    x_dev_telegram_id: Optional[str] = Header(None, alias="X-Dev-Telegram-Id"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    # 1. Telegram WebApp initData validation takes FIRST priority
    init_data = x_telegram_init_data
    if not init_data and authorization and authorization.startswith("twa "):
        init_data = authorization[4:]

    if init_data:
        verified = verify_telegram_init_data(init_data, settings.BOT_TOKEN)
        if verified and "user" in verified:
            u = verified["user"]
            tg_id = int(u.get("id"))
            return await get_or_create_user(
                db,
                telegram_id=tg_id,
                username=u.get("username"),
                first_name=u.get("first_name"),
                last_name=u.get("last_name")
            )

    # 2. Dev Mode Authentication (fallback when opened outside Telegram in local browser)
    if settings.DEV_AUTH_ENABLED and x_dev_telegram_id:
        try:
            dev_id = int(x_dev_telegram_id)
            if dev_id in settings.admin_id_list or dev_id in [5563980982, 123456789]:
                admin_id = settings.admin_id_list[0] if settings.admin_id_list else dev_id
                return await get_or_create_user(db, admin_id, "admin_luch", "Администратор", "Store")
            else:
                return await get_or_create_user(db, dev_id, "ivan_buyer", "Иван", "Покупатель")
        except ValueError:
            pass

    # 3. Default demo user if in local dev mode and nothing sent
    if settings.DEV_AUTH_ENABLED:
        return await get_or_create_user(db, 1110001, "ivan_buyer", "Иван", "Покупатель")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется авторизация через Telegram Mini App"
    )

async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.telegram_id not in settings.admin_id_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуются права администратора"
        )
    return current_user
