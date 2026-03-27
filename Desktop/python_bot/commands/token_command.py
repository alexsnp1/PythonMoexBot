from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.user_chat_registry import UserChatRegistry
from price.price_service import PriceService


router = Router()


def configure_token_commands(price_service: PriceService, chats: UserChatRegistry) -> None:
    @router.message(Command("set_token"))
    async def set_token(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        chats.remember(message.from_user.id, message.chat.id)

        parts = message.text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            await message.answer("Usage: /set_token <token>")
            return

        new_token = parts[1].strip()
        masked = PriceService.mask_token(new_token)

        ok = await asyncio.to_thread(price_service.is_token_valid, new_token)
        if not ok:
            await message.answer("❌ Token is invalid or expired\nToken NOT applied")
            return

        price_service.set_tradingview_token(new_token)
        await message.answer(f"✅ Token updated and valid\nToken: {masked}")

    @router.message(Command("token"))
    async def token_status(message: Message) -> None:
        if message.from_user is None:
            return
        chats.remember(message.from_user.id, message.chat.id)

        current = getattr(price_service, "_tv_auth_token", "").strip()
        if not current:
            await message.answer("⚠️ No TradingView token set")
            return

        ok = await asyncio.to_thread(price_service.is_token_valid, current)
        masked = PriceService.mask_token(current)
        status = "✅ valid" if ok else "❌ invalid / expired"
        await message.answer(f"🔑 Current token: {masked}\n\nStatus: {status}")

    @router.message(Command("remove_token"))
    async def remove_token(message: Message) -> None:
        if message.from_user is None:
            return
        chats.remember(message.from_user.id, message.chat.id)
        price_service.set_tradingview_token(None)
        await message.answer("🗑 Token removed")

