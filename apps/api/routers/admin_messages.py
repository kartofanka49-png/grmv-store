from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from typing import Annotated
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db
from apps.api.models import BotBroadcast, BotMessage, BotOptOut, User
from apps.api.security import get_current_admin

router = APIRouter(prefix="/admin/messages", tags=["admin-messages"], dependencies=[Depends(get_current_admin)])


class ComposeMessage(BaseModel):
    request_id: UUID
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def audience():
    return select(User.id).where(User.telegram_id > 0, ~User.id.in_(select(BotOptOut.user_id)))


@router.get("/broadcasts")
async def broadcasts(db: AsyncSession = Depends(get_db)):
    recipients = await db.scalar(select(func.count()).select_from(audience().subquery()))
    records = (await db.scalars(select(BotBroadcast).order_by(BotBroadcast.created_at.desc()).limit(30))).all()
    counts = (await db.execute(select(BotMessage.broadcast_id, BotMessage.status, func.count())
                              .where(BotMessage.broadcast_id.in_([record.id for record in records]))
                              .group_by(BotMessage.broadcast_id, BotMessage.status))).all()
    totals = {}
    for broadcast_id, state, count in counts:
        totals.setdefault(broadcast_id, {})[state] = count
    return {"recipients": recipients, "broadcasts": [
        {"id": record.id, "body": record.body, "created_at": record.created_at, "counts": totals.get(record.id, {})}
        for record in records
    ]}


@router.post("/broadcasts", status_code=status.HTTP_202_ACCEPTED)
async def queue_broadcast(data: ComposeMessage, db: AsyncSession = Depends(get_db)):
    key = str(data.request_id)
    if not await db.get(BotBroadcast, key):
        recipients = (await db.scalars(audience())).all()
        if not recipients:
            raise HTTPException(409, "Пока нет получателей для рассылки.")
        db.add(BotBroadcast(id=key, body=data.body))
        try:
            await db.flush()
            db.add_all(BotMessage(user_id=user_id, broadcast_id=key, status="pending") for user_id in recipients)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if not await db.get(BotBroadcast, key):
                raise
    return {"id": key}


@router.get("/chats")
async def chats(db: AsyncSession = Depends(get_db)):
    latest = (select(BotMessage.user_id, func.max(BotMessage.id).label("message_id"))
              .where(BotMessage.broadcast_id.is_(None)).group_by(BotMessage.user_id).subquery())
    rows = (await db.execute(select(User, BotMessage).join(latest, latest.c.user_id == User.id)
                            .join(BotMessage, BotMessage.id == latest.c.message_id)
                            .order_by(BotMessage.id.desc()))).all()
    return [{"id": user.id, "name": " ".join(filter(None, (user.first_name, user.last_name))),
             "username": user.username, "last_message": message.body} for user, message in rows]


@router.get("/chats/{user_id}")
async def chat(user_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(BotMessage)
                            .where(BotMessage.user_id == user_id, BotMessage.broadcast_id.is_(None))
                            .order_by(BotMessage.id.desc()).limit(100))).all()
    return [{"id": message.id, "body": message.body, "status": message.status,
             "created_at": message.created_at} for message in reversed(rows)]


@router.post("/chats/{user_id}", status_code=status.HTTP_202_ACCEPTED)
async def queue_reply(user_id: int, data: ComposeMessage, db: AsyncSession = Depends(get_db)):
    if not await db.scalar(select(BotMessage.id).where(BotMessage.user_id == user_id,
                                                        BotMessage.status == "received").limit(1)):
        raise HTTPException(404, "Клиент ещё не писал в бот.")
    key = str(data.request_id)
    existing = await db.scalar(select(BotMessage).where(BotMessage.request_id == key))
    if existing:
        if existing.user_id != user_id or existing.body != data.body:
            raise HTTPException(409, "Этот запрос уже использован.")
        return {"queued": True}
    db.add(BotMessage(user_id=user_id, request_id=key, body=data.body, status="pending"))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(BotMessage).where(BotMessage.request_id == key))
        if not existing or existing.user_id != user_id or existing.body != data.body:
            raise
    return {"queued": True}
