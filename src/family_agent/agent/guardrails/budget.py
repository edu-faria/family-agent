"""Rate + spend limits. Enforced before any model call — no LLM needed."""

from __future__ import annotations

from family_agent.config import Limits
from family_agent.persistence.repositories import AuditRepo


class BudgetExceeded(Exception):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class BudgetGuard:
    def __init__(self, audit: AuditRepo, limits: Limits) -> None:
        self.audit = audit
        self.limits = limits

    def check(self, member_id: int, locale: str = "pt") -> None:
        if self.audit.messages_today(member_id) >= self.limits.per_member_daily_messages:
            raise BudgetExceeded(_msg(locale, "daily"))
        if self.audit.messages_today_global() >= self.limits.global_daily_messages:
            raise BudgetExceeded(_msg(locale, "daily"))
        if self.audit.spend_this_month(member_id) >= self.limits.per_member_monthly_usd:
            raise BudgetExceeded(_msg(locale, "monthly"))
        if self.audit.spend_this_month(None) >= self.limits.global_monthly_usd:
            raise BudgetExceeded(_msg(locale, "monthly"))


def _msg(locale: str, kind: str) -> str:
    pt = {
        "daily": "Limite de mensagens de hoje atingido. Tenta de novo amanhã.",
        "monthly": "Orçamento do mês atingido. Fala com o admin da família.",
    }
    de = {
        "daily": "Tageslimit an Nachrichten erreicht. Morgen wieder.",
        "monthly": "Monatsbudget erreicht. Bitte den Familien-Admin fragen.",
    }
    return (de if locale == "de" else pt)[kind]
