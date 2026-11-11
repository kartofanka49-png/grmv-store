import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import User as TelegramUser
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.database import AsyncSessionLocal
from apps.api.models import BotBroadcast, BotMessage, BotOptOut, User
from apps.api.security import get_or_create_user

logger = logging.getLogger(__name__)


async def register_user(profile: TelegramUser):
    async with AsyncSessionLocal() as db:
        try:
            user = await get_or_create_user(db, profile.id, profile.username, profile.first_name, profile.last_name)
        except IntegrityError:
            await db.rollback()
            user = await get_or_create_user(db, profile.id, profile.username, profile.first_name, profile.last_name)
        return user.id


async def set_subscription(profile: TelegramUser, subscribed: bool):
    user_id = await register_user(profile)
    async with AsyncSessionLocal() as db:
        if subscribed:
            await db.execute(delete(BotOptOut).where(BotOptOut.user_id == user_id))
        elif not await db.get(BotOptOut, user_id):
            db.add(BotOptOut(user_id=user_id))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if subscribed or not await db.get(BotOptOut, user_id):
                raise


async def record_message(profile: TelegramUser, message_id: int, body: str):
    user_id = await register_user(profile)
    async with AsyncSessionLocal() as db:
        db.add(BotMessage(user_id=user_id, incoming_message_id=message_id, body=body, status="received"))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if not await db.scalar(select(BotMessage.id).where(
                BotMessage.user_id == user_id, BotMessage.incoming_message_id == message_id
            )):
                raise


async def finish_message(message_id, state):
    async with AsyncSessionLocal() as db:
        await db.execute(update(BotMessage).where(BotMessage.id == message_id).values(status=state))
        await db.commit()


async def deliver_next(bot: Bot) -> bool:
    async with AsyncSessionLocal() as db:
        record = (await db.execute(
            select(BotMessage, User.telegram_id, BotBroadcast.body)
            .join(User, User.id == BotMessage.user_id)
            .outerjoin(BotBroadcast, BotBroadcast.id == BotMessage.broadcast_id)
            .where(BotMessage.status == "pending")
            .order_by(BotMessage.broadcast_id.is_not(None), BotMessage.id).limit(1)
        )).first()
        if not record:
            return False
        message, telegram_id, broadcast_body = record
        message_id = message.id
        body = broadcast_body if message.broadcast_id else message.body
        if message.broadcast_id and await db.get(BotOptOut, message.user_id):
            message.status = "skipped"
            await db.commit()
            return True
        claimed = await db.execute(update(BotMessage).where(BotMessage.id == message_id,
                                                           BotMessage.status == "pending").values(status="sending"))
        await db.commit()
        if claimed.rowcount != 1:
            return True

    try:
        await bot.send_message(telegram_id, body)
    except TelegramRetryAfter as error:
        await finish_message(message_id, "pending")
        await asyncio.sleep(error.retry_after + 1)
    except (TelegramForbiddenError, TelegramBadRequest):
        await finish_message(message_id, "failed")
    except (TelegramNetworkError, TelegramAPIError):
        # The request may already have reached Telegram. Avoid sending it twice.
        await finish_message(message_id, "unknown")
    else:
        await finish_message(message_id, "sent")
    return True


async def run_outbox(bot: Bot):
    recover = True
    while True:
        try:
            if recover:
                async with AsyncSessionLocal() as db:
                    await db.execute(update(BotMessage).where(BotMessage.status == "sending").values(status="unknown"))
                    await db.commit()
                recover = False
            await asyncio.sleep(0.05 if await deliver_next(bot) else 1)
        except SQLAlchemyError:
            logger.warning("Telegram message queue is temporarily unavailable")
            recover = True
            await asyncio.sleep(3)
