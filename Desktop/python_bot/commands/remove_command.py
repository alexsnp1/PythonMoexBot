from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import logging

from db.database_service import DatabaseService


router = Router()


def configure_remove_command(db: DatabaseService) -> None:
    @router.message(Command("remove"))
    async def remove_rule(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer("Usage: /remove <n>  (rule number from /list, starting at 1)")
            return

        try:
            rule_number = int(parts[1])
        except ValueError:
            await message.answer("Rule number must be an integer.")
            return

        rules = db.list_rules(user_id=message.from_user.id)
        index = rule_number - 1
        if index < 0 or index >= len(rules):
            await message.answer("Rule not found")
            return

        rule = rules[index]
        logging.getLogger("SpreadScheduler").info(
            "Removing rule #%s (id=%s): %s | upper=%s lower=%s",
            rule.rule_number,
            rule.id,
            rule.formula,
            rule.upper_bound,
            rule.lower_bound,
        )
        removed = db.remove_rule(user_id=message.from_user.id, rule_number=rule_number)
        if removed:
            await message.answer(
                f"✅ Removed rule #{rule_number}: {rule.formula} | upper={rule.upper_bound} lower={rule.lower_bound}"
            )
        else:
            await message.answer("Rule not found")

