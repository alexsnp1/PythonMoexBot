from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from commands.add_command import configure_add_command, router as add_router
from commands.edit_command import configure_edit_command, router as edit_router
from commands.list_command import configure_list_command, router as list_router
from commands.remove_command import configure_remove_command, router as remove_router
from commands.token_command import configure_token_commands, router as token_router
from bot.user_chat_registry import UserChatRegistry
from db.database_service import DatabaseService
from price.price_service import PriceService


@dataclass(slots=True)
class TelegramBotApp:
    bot: Bot
    dispatcher: Dispatcher

    async def run(self) -> None:
        await self.dispatcher.start_polling(self.bot)


def build_telegram_bot(
    token: str,
    db: DatabaseService,
    price_service: PriceService,
    chats: UserChatRegistry,
) -> TelegramBotApp:
    logging.getLogger("aiogram").setLevel(logging.INFO)

    bot = Bot(token=token)
    dispatcher = Dispatcher()

    base_router = Router()

    @base_router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if message.from_user is not None:
            chats.remember(message.from_user.id, message.chat.id)
        await message.answer(
            "Spread monitor bot is running.\n"
            "Commands:\n"
            "/add <formula> <upper> <lower>\n"
            "/list\n"
            "/remove <n>\n"
            "/edit <n> <upper> <lower>\n"
            "/set_token <token>\n"
            "/token\n"
            "/remove_token\n"
            "(n = rule number from /list, starting at 1)"
        )

    configure_add_command(db, chats=chats)
    configure_list_command(db, chats=chats)
    configure_remove_command(db)
    configure_edit_command(db)
    configure_token_commands(price_service, chats)

    dispatcher.include_router(base_router)
    dispatcher.include_router(add_router)
    dispatcher.include_router(list_router)
    dispatcher.include_router(remove_router)
    dispatcher.include_router(edit_router)
    dispatcher.include_router(token_router)

    return TelegramBotApp(bot=bot, dispatcher=dispatcher)

