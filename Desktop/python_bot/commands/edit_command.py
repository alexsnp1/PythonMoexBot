from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from db.database_service import DatabaseService


router = Router()


def configure_edit_command(db: DatabaseService) -> None:
    @router.message(Command("edit"))
    async def edit_rule(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return

        parts = message.text.split(maxsplit=3)
        if len(parts) != 4:
            await message.answer("Usage: /edit <id> <upper> <lower>")
            return

        _, rule_id_str, upper_str, lower_str = parts
        try:
            rule_id = int(rule_id_str)
            upper = float(upper_str)
            lower = float(lower_str)
        except ValueError:
            await message.answer("id must be integer, upper/lower must be numbers.")
            return

        updated = db.update_rule_bounds(
            user_id=message.from_user.id,
            rule_id=rule_id,
            upper=upper,
            lower=lower,
        )
        if updated:
            await message.answer(f"Rule #{rule_id} updated: upper={upper}, lower={lower}")
        else:
            await message.answer("Rule not found or does not belong to you.")

