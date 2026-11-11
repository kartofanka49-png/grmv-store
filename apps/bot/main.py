import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo

from apps.api.config import settings
from apps.bot.messages import record_message, register_user, run_outbox, set_subscription

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("grmv_bot")
dp = Dispatcher()
dp.message.filter(F.chat.type == "private")


def button(text: str, path: str) -> InlineKeyboardButton:
    url = settings.APP_BASE_URL.rstrip("/") + path
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def shop_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [button("Открыть магазин", "/")],
        [button("Мои заказы", "/orders"), button("Калькулятор", "/calculator")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def start_shop(message: Message):
    if message.from_user:
        await register_user(message.from_user)
        await open_shop(message)


@dp.message(Command("shop", "help"))
async def open_shop(message: Message):
    if not message.from_user:
        return
    await message.answer(
        "GRMV xLUCH store\nОткройте витрину, отправьте заявку на выкуп по ссылке или проверьте заказ.\n"
        "Есть вопрос? Напишите его прямо в этот чат.",
        reply_markup=shop_keyboard(),
    )


@dp.message(Command("orders"))
async def open_orders(message: Message):
    await message.answer("Ваши заказы в Mini App.", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[button("Мои заказы", "/orders")]]))


@dp.message(Command("calculator"))
async def open_calculator(message: Message):
    await message.answer("Рассчитайте стоимость товара с доставкой.", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[button("Калькулятор", "/calculator")]]))


@dp.message(Command("support"))
async def support(message: Message):
    await message.answer("Напишите вопрос в этот чат. Администратор ответит через бота.")


@dp.message(Command("stop", "subscribe"))
async def subscription(message: Message, command):
    if message.from_user:
        subscribed = command.command == "subscribe"
        await set_subscription(message.from_user, subscribed)
        await message.answer("Рассылка включена." if subscribed else "Рассылка отключена. Включить снова — /subscribe.")


@dp.message(F.text, ~F.text.startswith("/"))
async def receive_message(message: Message):
    if message.from_user and message.text:
        await record_message(message.from_user, message.message_id, message.text)


async def main():
    if not settings.BOT_TOKEN or not settings.APP_BASE_URL.startswith("https://"):
        raise SystemExit("Set a Telegram bot token and an HTTPS Mini App address.")
    async with Bot(token=settings.BOT_TOKEN) as bot:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Магазин", web_app=WebAppInfo(url=settings.APP_BASE_URL.rstrip("/") + "/")))
        await bot.set_my_commands([
            BotCommand(command="start", description="Открыть магазин"),
            BotCommand(command="shop", description="Каталог и выкуп по ссылке"),
            BotCommand(command="orders", description="Мои заказы"),
            BotCommand(command="calculator", description="Калькулятор стоимости"),
            BotCommand(command="help", description="Как открыть Mini App"),
            BotCommand(command="support", description="Написать в поддержку"),
            BotCommand(command="stop", description="Отписаться от рассылки"),
            BotCommand(command="subscribe", description="Подписаться на рассылку"),
        ])
        identity = await bot.get_me()
        logger.info("Mini App connected to @%s", identity.username)
        worker = asyncio.create_task(run_outbox(bot))
        try:
            await dp.start_polling(bot, close_bot_session=False)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
