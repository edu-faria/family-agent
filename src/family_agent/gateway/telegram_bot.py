"""Telegram adapter (long polling — no inbound ports).

Responsibilities only:
  - receive updates, drop anyone not on the allowlist
  - rate-limit per user
  - normalize to InboundMessage / render OutboundMessage
  - show a typing indicator while the manager works

All decisions and side effects happen downstream in ConversationManager.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from family_agent.config import Settings
from family_agent.conversation import ConversationManager
from family_agent.gateway.access import Allowlist, RateLimiter
from family_agent.logging_setup import get_logger
from family_agent.types import InboundMessage, OutboundMessage

log = get_logger(__name__)


class TelegramGateway:
    def __init__(self, settings: Settings, manager: ConversationManager) -> None:
        self.settings = settings
        self.manager = manager
        self.allowlist = Allowlist(settings.allowlist)
        self.rate = RateLimiter(limit=20, window_seconds=60)
        self.app = Application.builder().token(settings.telegram_bot_token).build()
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        self.app.add_handler(CallbackQueryHandler(self._on_callback))

    def run(self) -> None:
        log.info("telegram.start", allowlisted=len(self.settings.allowlist))
        self.app.run_polling(allowed_updates=["message", "callback_query"])

    # -- handlers ----------------------------------------------------------------
    async def _on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        chat = update.effective_chat
        if user is None or chat is None or update.message is None:
            return
        if not self.allowlist.permits(user.id):
            await update.message.reply_text("Desculpa, não te conheço. Este assistente é privado.")
            log.warning("telegram.denied", user_id=user.id)
            return
        if not self.rate.allow(user.id):
            await update.message.reply_text("Devagar 🙂 tenta daqui a um bocado.")
            return

        member = self.settings.member(user.id)
        msg = InboundMessage(
            member_id=user.id,
            member_name=member.display_name if member else (user.first_name or "?"),
            locale=member.locale if member else self.settings.default_locale,
            chat_id=chat.id,
            is_group=chat.type in ("group", "supergroup"),
            text=update.message.text or "",
            received_at=datetime.now(timezone.utc),
        )
        await self._dispatch(update, msg)

    async def _on_callback(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user = update.effective_user
        chat = update.effective_chat
        if query is None or user is None or chat is None:
            return
        await query.answer()
        if not self.allowlist.permits(user.id):
            return
        member = self.settings.member(user.id)
        msg = InboundMessage(
            member_id=user.id,
            member_name=member.display_name if member else (user.first_name or "?"),
            locale=member.locale if member else self.settings.default_locale,
            chat_id=chat.id,
            is_group=chat.type in ("group", "supergroup"),
            text="",
            received_at=datetime.now(timezone.utc),
            callback_data=query.data,
        )
        await self._dispatch(update, msg)

    # -- shared ---------------------------------------------------------------
    async def _dispatch(self, update: Update, msg: InboundMessage) -> None:
        try:
            await update.effective_chat.send_action("typing")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
        # ConversationManager is synchronous (SQLite + SDKs); run it off the event loop.
        outs: list[OutboundMessage] = await asyncio.to_thread(self.manager.handle, msg)
        for out in outs:
            markup = None
            if out.buttons:
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(label, callback_data=data)] for label, data in out.buttons]
                )
            await self.app.bot.send_message(chat_id=out.chat_id, text=out.text, reply_markup=markup)
