# family-agent

A chat-first family plan manager: a **Telegram bot** backed by an **LLM agent**,
self-hosted on a home Docker host. It holds the data itself (no external calendar
sync) and everyone in the family talks to it in normal language — Portuguese by
default, German words welcome.

Today it covers:

- **Calendar** — add / change / delete / query appointments. On add or move it
  runs a conflict check (time overlap, **shared-car clash**, tight turnaround,
  other things the same day) and shows every warning before you confirm.
- **Shopping** — add items, mark bought, show the list.

New domains are plug-ins: drop a package under
[`src/family_agent/capabilities/`](src/family_agent/capabilities/) and list it in
`config.toml`. The core doesn't change. See
[docs/architecture.md](docs/architecture.md).

## How it works (one message)

```
Telegram (long polling)
  → gateway: allowlist + rate limit + normalize
  → budget guard (per-member / global, daily msgs + monthly $)
  → input guard (length, injection scan, out-of-scope pre-filter)
  → router (cheap model): in scope? which capability? plain read or full agent?
  → executor (Claude Opus, GPT fallback): bounded tool-calling loop
      → tool dispatcher: schema-validate → authz → CONFIRM if it writes → audit
      → capability logic → SQLite
  → output guard (leak scrub, Telegram chunking) → reply
```

The LLM has **no** database, shell, filesystem or network of its own — only the
registered tools. Every write is gated behind a Yes/No button. Everything is
written to `audit_log`.

## Run it

```bash
cp .env.example .env      # fill in bot token, API keys, FAMILY_ALLOWLIST
docker compose up -d --build
docker compose logs -f family-agent
```

`config.toml` holds non-secret settings (models, timezone, limits, enabled
capabilities). Data lives in the `familydata` volume at `/data/family.db`; the
`backup` sidecar snapshots it nightly to `/data/backups/`.

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

## Status

Scaffold. The conflict checker, tool registry/dispatcher, confirmation gate,
migrations and guardrail structure are implemented; the LLM provider wiring and
Telegram glue are in place but lightly exercised. Proactive alerts (reminder
pushes, digests) are deliberately deferred — the scheduler and
`appointment_reminder` table are the hook points.
