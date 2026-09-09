"""Boot: load config -> open DB + migrate -> build registry -> start bot + scheduler."""

from __future__ import annotations

import sys

from family_agent.agent.guardrails import BudgetGuard, InputGuard
from family_agent.agent.loop import Executor
from family_agent.agent.providers import Providers
from family_agent.agent.router import Router
from family_agent.capabilities import load_capabilities, migration_dirs
from family_agent.config import load_settings
from family_agent.conversation import ConversationManager
from family_agent.gateway import TelegramGateway
from family_agent.logging_setup import configure_logging, get_logger
from family_agent.persistence.db import Database
from family_agent.persistence.migrations import run_migrations
from family_agent.persistence.repositories import (
    AuditRepo,
    ConversationRepo,
    MemberRepo,
    PendingActionRepo,
)
from family_agent.scheduler import SchedulerService
from family_agent.tools.dispatcher import ToolDispatcher
from family_agent.tools.registry import ToolRegistry


def build_manager(settings, db: Database) -> ConversationManager:
    audit = AuditRepo(db)
    conversations = ConversationRepo(db)
    pending = PendingActionRepo(db)

    registry = ToolRegistry()
    for cap in load_capabilities(settings.enabled_capabilities):
        registry.register(cap)

    providers = Providers(settings)
    dispatcher = ToolDispatcher(registry, audit)
    router = Router(providers, audit, settings.agent.router_model, list(settings.enabled_capabilities))
    executor = Executor(providers, registry, dispatcher, audit, settings)

    return ConversationManager(
        settings=settings,
        conversations=conversations,
        audit=audit,
        pending=pending,
        budget=BudgetGuard(audit, settings.limits),
        input_guard=InputGuard(settings.limits.max_inbound_chars),
        router=router,
        executor=executor,
    )


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    log = get_logger("family_agent")

    if not settings.telegram_bot_token:
        log.error("config.missing", what="TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    if not settings.allowlist:
        log.error("config.missing", what="FAMILY_ALLOWLIST")
        sys.exit(1)

    db = Database(settings.db_path)
    run_migrations(db, migration_dirs(settings.enabled_capabilities))

    # Seed members from env so names/locales are available immediately.
    members = MemberRepo(db)
    for m in settings.members.values():
        members.upsert(m.telegram_user_id, m.display_name, m.locale)

    scheduler = SchedulerService(settings.timezone)
    scheduler.start()

    manager = build_manager(settings, db)
    gateway = TelegramGateway(settings, manager)

    log.info("boot.ready", capabilities=list(settings.enabled_capabilities), tz=settings.timezone)
    try:
        gateway.run()
    finally:
        scheduler.shutdown()
        db.close()


if __name__ == "__main__":
    main()
