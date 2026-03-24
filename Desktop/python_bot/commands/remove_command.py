from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from db.database_service import DatabaseService


router = Router()


def configure_remove_command(db: DatabaseService) -> None:
    @router.message(Command("remove"))
    async def remove_rule(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer("Usage: /remove <id>")
            return

        try:
            rule_id = int(parts[1])
        except ValueError:
            await message.answer("Rule id must be an integer.")
            return

        removed = db.remove_rule(user_id=message.from_user.id, rule_id=rule_id)
        if removed:
            await message.answer(f"Rule #{rule_id} removed.")
        else:
            await message.answer("Rule not found or does not belong to you.")

