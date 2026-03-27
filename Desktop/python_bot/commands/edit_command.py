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
            await message.answer("Usage: /edit <n> <upper> <lower>  (n = rule number from /list)")
            return

        _, rule_n_str, upper_str, lower_str = parts
        try:
            rule_number = int(rule_n_str)
            upper = float(upper_str)
            lower = float(lower_str)
        except ValueError:
            await message.answer("Rule number must be an integer; upper/lower must be numbers.")
            return

        rules = db.list_rules(user_id=message.from_user.id)
        index = rule_number - 1
        if index < 0 or index >= len(rules):
            await message.answer("Rule not found")
            return

        updated = db.update_rule_bounds(
            user_id=message.from_user.id,
            rule_number=rule_number,
            upper=upper,
            lower=lower,
        )
        if updated:
            await message.answer(f"Rule #{rule_number} updated: upper={upper}, lower={lower}")
        else:
            await message.answer("Rule not found")

