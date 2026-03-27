from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.user_chat_registry import UserChatRegistry
from db.database_service import DatabaseService
from parser.formula_parser import FormulaParser


router = Router()


def configure_add_command(db: DatabaseService, chats: UserChatRegistry | None = None) -> None:
    @router.message(Command("add"))
    async def add_rule(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        if chats is not None:
            chats.remember(message.from_user.id, message.chat.id)

        parts = message.text.split(maxsplit=3)
        if len(parts) != 4:
            await message.answer("Usage: /add <formula> <upper> <lower>")
            return

        _, formula, upper_str, lower_str = parts

        try:
            upper = float(upper_str)
            lower = float(lower_str)
        except ValueError:
            await message.answer("Upper and lower must be numbers.")
            return

        parser = FormulaParser()
        symbols = parser.extract_symbols(formula)
        if not symbols:
            await message.answer("Formula must contain at least one symbol like RUS:SV1! .")
            return

        rule_number = db.add_rule(user_id=message.from_user.id, formula=formula, upper=upper, lower=lower)
        await message.answer(
            f"Rule #{rule_number} added.\nFormula: {formula}\nUpper: {upper}\nLower: {lower}"
        )

