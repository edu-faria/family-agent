# family-agent — architecture

## 1. Purpose & principles

A private, chat-first manager for one family, run on a home Docker host.

1. **Chat is the only interface.** Telegram, in natural language (Portuguese
   default; German words kept verbatim). No web UI, no app.
2. **The app owns the data.** SQLite is the single source of truth. No calendar
   sync — ever.
3. **Domains are plug-ins.** Calendar and shopping are *capabilities* registered
   against a stable core. New domains ("chores", "meals", "meds", "budget") =
   a new package + a config flag. Core code doesn't change.
4. **The LLM is boxed in.** No database, shell, filesystem or network of its own —
   only a typed, registered tool catalog. Every write passes a Yes/No gate.
5. **Local-first and cheap.** Long polling (no open ports). A cheap model routes;
   the expensive model only runs when reasoning is actually needed. Hard budget
   caps.

### Locked decisions

| Area | Decision |
|---|---|
| Language / runtime | Python 3.12, single service |
| LLM providers | Anthropic (Claude, primary) + OpenAI (GPT, fallback) |
| Alerts | On request only for now; scheduler + `appointment_reminder` table are hooks for later proactive push |
| Persistence | SQLite file on a Docker volume + nightly `sqlite3 .backup` sidecar |
| Timezone / locale | `Europe/Berlin`, default reply locale `pt` |

## 2. Deployment

`docker-compose` with two services:

| Container | Role |
|---|---|
| `family-agent` | Telegram client + agent loop + domain logic + (dormant) scheduler |
| `backup` | Nightly consistent snapshot of the data volume, retention, optional off-host copy |

- Volume `familydata:/data` → `family.db`, `/data/backups/`.
- Secrets in `.env` (`TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `FAMILY_ALLOWLIST`, `FAMILY_MEMBERS`). Non-secrets in `config.toml`.
- **Telegram long polling** → no inbound firewall rules, no public URL, no proxy.

## 3. Internal layers

```
Telegram update
  │
[1] Gateway (src/family_agent/gateway/)
  │   allowlist gate • per-user rate limit • normalize → InboundMessage • typing indicator
  ▼
[2] ConversationManager (src/family_agent/conversation/)
  │   per-chat lock • rolling history • pending-confirmation state machine
  ▼
[3] Budget guard  → per-member & global daily message caps, monthly $ caps (no model call)
[4] Input guard   → length cap • injection pattern scan (flag, don't block) • out-of-scope pre-filter
  ▼
[5] Router (agent/router.py)  cheap model
  │   in scope? • which capability(ies)? • plain read (answer now) or full executor?
  ▼
[6] Executor (agent/loop.py)  Claude Opus primary, GPT fallback
  │   bounded manual tool-calling loop:
  │     • only the routed capabilities' tools are exposed
  │     • ≤ max_tool_calls_per_turn, wall-clock deadline, max output tokens
  ▼
[7] ToolDispatcher (tools/dispatcher.py)
  │   look up tool • pydantic-validate input • authz • bulk cap
  │   • if writes and not pre-confirmed → raise ConfirmationRequired  ┐
  │   • else run handler, audit outcome                                │
  ▼                                                                    │
[8] Capability logic (capabilities/<name>/)  → SQLite                  │
  ▲                                                                    │
  └──────────────── ConfirmationRequired bubbles up ──────────────────┘
                    → manager persists PendingAction, sends Yes/No buttons
                    → on ✅ the manager calls executor.resume_confirmed(),
                      which runs that one tool with pre_confirmed=True

[9] Output guard (agent/guardrails/output.py) → leak scrub • Telegram 4096-char chunking
```

Every inbound message, model call (with tokens + estimated cost), tool call (with
args), and confirmation decision is written to `audit_log`. Fail closed: any
guardrail error or unhandled exception → apologise, change nothing.

## 4. The plug-in system

Each domain implements the `Capability` protocol
([`tools/registry.py`](../src/family_agent/tools/registry.py)):

```python
class Capability(Protocol):
    name: str
    def tools(self) -> list[Tool]: ...
    def system_prompt_fragment(self) -> str: ...
    def scheduled_jobs(self) -> list: ...   # empty for now
```

A `Tool` carries its own safety metadata:

```python
Tool(
    name="calendar.add_appointment",   # namespaced
    description=...,
    input_model=AddAppointmentInput,   # pydantic → JSON schema the LLM sees
    handler=add_appointment,
    writes=True,                       # → confirmation gate
    authz="family",                   # "family" | "admin"
    summarize=_summarize_add,          # builds the human Yes/No text (incl. conflicts)
)
```

`ToolRegistry` assembles the executor's tool catalog and system prompt from
whatever capabilities are enabled in `config.toml`. `capabilities/loader.py`
imports `capabilities/<name>/capability.py::get_capability()` and its
`migrations/*.sql`.

**Adding a domain:** create `capabilities/chores/` with `capability.py`,
`schemas.py`, `logic.py`, `tools.py`, `prompt.md`, `migrations/0001_initial.sql`;
add `"chores"` to `enabled_capabilities`. No core edits.

## 5. Data model

**Core** ([`persistence/migrations_sql/0001_core.sql`](../src/family_agent/persistence/migrations_sql/0001_core.sql))

- `family_member` — telegram_user_id, display_name, role, locale, active
- `conversation_turn` — chat_id, member_id, role, content, ts (rolling window)
- `audit_log` — kind, tool_name, model, input_json, result_summary, tokens, cost_usd
- `pending_action` — token, tool_name, tool_input(JSON), human_summary, decision
- `schema_migrations`

**calendar** ([`capabilities/calendar/migrations/0001_initial.sql`](../src/family_agent/capabilities/calendar/migrations/0001_initial.sql))

- `appointment` — title, `starts_at`/`ends_at` (ISO-8601 **UTC**), all_day,
  location, notes, owner_member_id, `attendees_json`, **`car_needed`**
  (`yes`|`no`|`maybe`|`unknown`), **`driver_member_id`**, `travel_buffer_minutes`,
  `rrule`, created_by, timestamps
- `appointment_reminder` — appointment_id, offset_minutes, sent_at *(rows exist
  now; the sender is a future feature)*

**shopping** — `shopping_list`, `shopping_item` (name, qty, unit, category,
`needed_by`, status `needed`|`bought`|`removed`, added_by/at, bought_at)

All datetimes stored UTC, rendered in `Europe/Berlin`. `family_member.locale`
drives reply language and date formatting.

## 6. Calendar conflict & relevance check

[`capabilities/calendar/conflicts.py`](../src/family_agent/capabilities/calendar/conflicts.py)
— pure logic, unit-tested. Run before every `add` / `update`; findings go into the
Yes/No prompt. Severity order:

| Severity | Trigger |
|---|---|
| `HARD` ⛔ | proposed `[start,end]` overlaps an existing appointment (notes if a shared attendee) |
| `CAR` 🚗 | proposed `car_needed ∈ {yes,maybe}` **and** another car-needing appointment falls within the overlap **± travel buffer** on each side |
| `TURNAROUND` ⏱️ | no time overlap, but within buffer of another appointment at a *different* location |
| `INFO` ℹ️ | same day, not overlapping — context only |

`HARD` and `CAR` are blockers: still overridable, but only on an explicit second
confirm. Also exposed as read tools: `calendar.check_car_availability`, and
`list_appointments` for "what's on…".

Example Yes/No message:

```
Adicionar **Dentista (Lena)**
· ter 16/09 15:00–16:00
· quem: Lena
· 🚗 carro: yes (motorista: Rafael)
🚗 O carro já está reservado para "Reunião escola" (16/09 14:00–15:30).
ℹ️ No mesmo dia: "Compras" às 10:00.

Confirmar?           [✅ Sim] [❌ Não]
```

## 7. Agent & models

Config-driven ([`config.toml`](../config.toml) `[agent]`):

| Role | Default | Job |
|---|---|---|
| `router_model` | `claude-haiku-4-5` | scope check, capability routing, "is a plain read enough?" |
| `primary_model` | `claude-opus-5` | the tool-calling executor loop (switch to `claude-sonnet-5` to cut cost) |
| `fallback_model` | `gpt-4o` | used when the primary provider errors / times out |

[`agent/providers.py`](../src/family_agent/agent/providers.py) exposes a
provider-neutral `complete()`; Anthropic via the official SDK with adaptive
thinking, OpenAI via its SDK. `estimate_cost()` feeds the budget guard.

Executor caps: `max_tool_calls_per_turn` (default 6), `turn_timeout_seconds`
(60), `max_output_tokens` (1200). Hitting a cap → it stops and asks the family.

## 8. Guardrails (layered)

1. **Identity** — `FAMILY_ALLOWLIST`; unknown Telegram id never reaches a model.
2. **Rate + budget** — per-member/global daily message caps; per-member/global
   monthly USD caps from `audit_log`. Enforced with no model call.
3. **Input** — length cap; prompt-injection pattern scan (message is wrapped as
   untrusted data, not dropped); out-of-scope pre-filter (weather/news/coding →
   canned decline, no executor).
4. **Tool layer** — LLM has only registered tools; every input pydantic-validated
   (invalid → structured error back to the model); `writes=True` → Yes/No gate;
   per-call bulk cap; per-tool authz.
5. **Output** — scrub system-prompt / key-shaped leaks; chunk to 4096 chars.
6. **Audit** — everything, with cost.
7. **Fail closed** — transactional writes; on any error, change nothing.

## 9. Conversation handling

- History: last `history_turns` from `conversation_turn`, oldest-first.
- One `threading.Lock` per `chat_id` — no write races between rapid messages.
- Confirmations are persisted (`pending_action`), so a restart doesn't lose them;
  15-minute TTL; resolved by `confirm:<token>` / `reject:<token>` callback data.
- Group chats and DMs both supported; writes attributed to the sender.

## 10. Repo map

```
src/family_agent/
  main.py                  boot & wiring
  config.py                config.toml + env overrides
  types.py                 InboundMessage, OutboundMessage, TurnResult, PendingAction
  gateway/                 telegram_bot.py, access.py (allowlist, rate limit)
  conversation/manager.py  orchestration + locking + confirmation state machine
  agent/
    router.py              cheap classifier
    loop.py                bounded executor
    providers.py           Anthropic + OpenAI, routing, fallback, cost estimate
    guardrails/            budget.py, input.py, output.py
  tools/
    registry.py            Capability / Tool / ToolContext / ConfirmationRequired
    dispatcher.py          validate • authz • gate • audit
  capabilities/
    loader.py
    calendar/  {capability,schemas,logic,conflicts,tools}.py, prompt.md, migrations/
    shopping/  {capability,schemas,logic,tools}.py, prompt.md, migrations/
  persistence/             db.py (SQLite/WAL), migrations.py, repositories.py, migrations_sql/
  scheduler/service.py     APScheduler, dormant — hook for proactive alerts
  observability/status.py  admin /status summary helper
tests/                     conflict checker, confirmation gate
```

## 11. Deliberately deferred

- **Proactive alerts** — reminder pushes, morning digest, low-stock nudges.
  Hooks: `SchedulerService`, `appointment_reminder`, `Capability.scheduled_jobs()`.
- **Recurrence editing** — `rrule` is stored; per-occurrence edits are out.
- **Voice messages** — Telegram voice → Whisper transcription, a gateway-level
  add, capability-independent.
- **Car as its own capability** — a second car / reserving the car without an
  appointment would move `car_needed`/`driver_member_id` into a `car_reservation`
  table. The current fields are forward-compatible.
- **Local models (Ollama)** — `providers.py` routing is the single place to point
  the router (then executor) at a local model if cloud privacy becomes a concern.
- **Postgres** — swap `persistence/db.py`; callers only use `query`/`execute`/
  `transaction`.
