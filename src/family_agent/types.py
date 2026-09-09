"""Shared value types passed between layers. No business logic here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    """A normalized message from the gateway, already identity-checked."""

    member_id: int
    member_name: str
    locale: str
    chat_id: int
    is_group: bool
    text: str
    received_at: datetime
    # For a callback-button press (confirmation Yes/No), this carries the token.
    callback_data: str | None = None


@dataclass
class OutboundMessage:
    chat_id: int
    text: str
    # When set, render inline buttons: list of (label, callback_data).
    buttons: list[tuple[str, str]] = field(default_factory=list)


class TurnStatus(str, Enum):
    ANSWERED = "answered"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REFUSED = "refused"
    ERROR = "error"


@dataclass
class TurnResult:
    status: TurnStatus
    reply: OutboundMessage
    # Populated when status == AWAITING_CONFIRMATION.
    pending_action: PendingAction | None = None


@dataclass
class PendingAction:
    """A write the agent proposed and the family must confirm before it runs."""

    token: str
    chat_id: int
    member_id: int
    tool_name: str
    tool_input: dict[str, Any]
    human_summary: str
    created_at: datetime
