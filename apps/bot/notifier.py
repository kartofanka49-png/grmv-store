import re
from html import escape
import logging
from typing import Optional
from decimal import Decimal
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from apps.api.config import settings

logger = logging.getLogger("grmv_notifier")

async def send_order_notification(telegram_id: int, message: str, keyboard: Optional[InlineKeyboardMarkup] = None):
    """
    Safely sends a notification message to a Telegram user.
    """
    if not settings.BOT_TOKEN or "Placeholder" in settings.BOT_TOKEN:
        logger.info(f"[DEV_NOTIFICATION to {telegram_id}]: {message}")
        return False

    try:
        async with Bot(token=settings.BOT_TOKEN) as bot:
            await bot.send_message(chat_id=telegram_id, text=message, parse_mode="HTML", reply_markup=keyboard)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление {telegram_id}: {e}")
        return False

async def notify_admins_new_order(
    order_number: str,
    customer_name: str,
    customer_telegram: Optional[str],
    total_rub: str,
    total_cny: str,
    items_desc: str,
    delivery_city: str
):
    """Уведомление администраторам о создании новой заявки на выкуп"""
    contact_str = f"@{customer_telegram.lstrip('@')}" if customer_telegram else "Не указан"
    text = (
        f"🆕 <b>Новая заявка на выкуп {order_number}!</b>\n\n"
        f"👤 <b>Покупатель:</b> {escape(customer_name)} ({escape(contact_str)})\n"
        f"📍 <b>Город доставки:</b> {escape(delivery_city)}\n"
        f"📦 <b>Состав заказа:</b>\n{escape(items_desc)}\n\n"
        f"💰 <b>Сумма к оплате:</b> {total_rub} ₽ ({total_cny} ¥)\n\n"
        f"⏳ <i>Ожидается перевод и загрузка чека покупателем.</i>"
    )

    buttons = []
    if customer_telegram and re.fullmatch(r"@[A-Za-z0-9_]{5,32}", customer_telegram):
        uname = customer_telegram.lstrip("@")
        buttons.append([InlineKeyboardButton(text="💬 Написать покупателю", url=f"https://t.me/{uname}")])

    web_url = settings.APP_BASE_URL.rstrip("/")
    if web_url.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="⚡ Открыть админку", web_app=WebAppInfo(url=f"{web_url}/admin"))])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    for admin_id in settings.admin_id_list:
        await send_order_notification(admin_id, text, keyboard=kb)

async def notify_admins_receipt_uploaded(
    order_number: str,
    order_id: int,
    customer_name: str,
    customer_telegram: Optional[str],
    total_rub: str,
    total_cny: str,
    items_desc: str,
    delivery_city: str,
    receipt_local_path: str
):
    text = (
        f"🧾 <b>Чек по заказу {escape(order_number)}</b>\n"
        f"Покупатель: {escape(customer_name)}\nСумма: {escape(total_rub)} ₽\n"
        "Откройте заказ, чтобы посмотреть чек и проверить перевод."
    )
    url = settings.APP_BASE_URL.rstrip("/") + f"/admin?order={order_id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть заказ", web_app=WebAppInfo(url=url))
    ]]) if url.startswith("https://") else None
    for admin_id in settings.admin_id_list:
        await send_order_notification(admin_id, text, keyboard)


async def notify_buyer_payment_approved(telegram_id: int, order_number: str):
    text = (
        f"✅ <b>Оплата по заказу {order_number} подтверждена!</b>\n\n"
        f"Администратор подтвердил поступление платежа. "
        f"Ваш заказ передан в работу на выкуп в Китае.\n\n"
        f"Вы можете отслеживать статус заказа в разделе «Мои заказы»."
    )
    await send_order_notification(telegram_id, text)

async def notify_buyer_status_update(telegram_id: int, order_number: str, status_label: str, comment: Optional[str] = None):
    text = f"📦 <b>Статус заказа {order_number} обновлен:</b>\n«{escape(status_label)}»"
    if comment:
        text += f"\n\n💬 Примечание: {escape(comment)}"
    await send_order_notification(telegram_id, text)

async def notify_admins_custom_buyout(
    request_id: int,
    customer_name: str,
    customer_telegram: Optional[str],
    link_or_title: str,
    size: Optional[str] = None,
    cny_price: Optional[Decimal] = None,
    notes: Optional[str] = None
):
    """Уведомление о запросе на индивидуальный выкуп по ссылке с POIZON"""
    contact_str = f"@{customer_telegram.lstrip('@')}" if customer_telegram else "Не указан"
    text = (
        f"🔍 <b>Новая заявка на выкуп по ссылке #{request_id}!</b>\n\n"
        f"👤 <b>Покупатель:</b> {escape(customer_name)} ({escape(contact_str)})\n"
        f"🔗 <b>Товар / Ссылка:</b> {escape(link_or_title)}\n"
    )
    if size:
        text += f"👟 <b>Размер:</b> {escape(size)}\n"
    if cny_price:
        text += f"💴 <b>Цена в POIZON:</b> {cny_price} ¥\n"
    if notes:
        text += f"💬 <b>Пожелания:</b> {escape(notes)}\n"

    buttons = []
    if customer_telegram and re.fullmatch(r"@[A-Za-z0-9_]{5,32}", customer_telegram):
        uname = customer_telegram.lstrip("@")
        buttons.append([InlineKeyboardButton(text="💬 Написать покупателю в Telegram", url=f"https://t.me/{uname}")])

    web_url = settings.APP_BASE_URL.rstrip("/")
    if web_url.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="Открыть заявки по ссылке", web_app=WebAppInfo(url=f"{web_url}/admin/buyouts"))])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    for admin_id in settings.admin_id_list:
        await send_order_notification(admin_id, text, keyboard=kb)

