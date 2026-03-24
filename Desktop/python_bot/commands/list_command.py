from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from db.database_service import DatabaseService


router = Router()


def configure_list_command(db: DatabaseService) -> None:
    @router.message(Command("list"))
    async def list_rules(message: Message) -> None:
        if message.from_user is None:
            return

        rules = db.list_rules(user_id=message.from_user.id)
        if not rules:
            await message.answer("No rules yet. Add one with /add <formula> <upper> <lower>.")
            return

        lines = ["Your rules:"]
        for rule in rules:
            lines.append(
                f"#{rule.id} | {rule.formula} | upper={rule.upper_bound} lower={rule.lower_bound}"
            )
        await message.answer("\n".join(lines))

