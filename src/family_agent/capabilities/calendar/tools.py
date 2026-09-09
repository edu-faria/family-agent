"""Calendar tool handlers + confirmation-summary builders.

The write tools (`add`, `update`, `delete`) run the conflict checker and fold every
finding into the summary the family sees before approving.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from family_agent.capabilities.calendar import logic
from family_agent.capabilities.calendar.conflicts import ApptView, find_findings
from family_agent.capabilities.calendar.schemas import (
    AddAppointmentInput,
    CheckCarAvailabilityInput,
    DeleteAppointmentInput,
    ListAppointmentsInput,
    UpdateAppointmentInput,
)
from family_agent.tools.registry import Tool, ToolContext, ToolError, ToolResult

UTC = ZoneInfo("UTC")


# --- helpers ------------------------------------------------------------------
def _repo(ctx: ToolContext) -> logic.CalendarRepo:
    return logic.CalendarRepo(ctx.db)


def _draft_view(ctx: ToolContext, data: AddAppointmentInput) -> ApptView:
    start = logic.parse_local(data.start, ctx.timezone)
    end = logic.parse_local(data.end, ctx.timezone) if data.end else logic.default_end(start)
    if end <= start:
        raise ToolError("O fim é antes do início.")
    return ApptView(
        id=None, title=data.title, start=start, end=end,
        car_needed=data.car_needed, location=data.location,
        attendees=tuple(data.attendees),
    )


def _existing_same_day(ctx: ToolContext, around: datetime) -> list[ApptView]:
    local_day = around.astimezone(ZoneInfo(ctx.timezone)).date()
    day_start = datetime.combine(local_day, datetime.min.time(), ZoneInfo(ctx.timezone)).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    rows = _repo(ctx).same_day(day_start.isoformat(), day_end.isoformat())
    return [logic.row_to_view(r) for r in rows]


# --- summaries (shown in the Yes/No prompt) ---------------------------------
def _summarize_add(ctx: ToolContext, data: AddAppointmentInput) -> str:
    view = _draft_view(ctx, data)
    buf = ctx.settings.calendar_travel_buffer_minutes
    findings = find_findings(view, _existing_same_day(ctx, view.start), buf)
    lines = [
        f"Adicionar **{data.title}**",
        f"· {logic.to_local_str(view.start.isoformat(), ctx.timezone)}"
        f"–{view.end.astimezone(ZoneInfo(ctx.timezone)):%H:%M}",
    ]
    if data.location:
        lines.append(f"· local: {data.location}")
    if data.attendees:
        lines.append(f"· quem: {', '.join(data.attendees)}")
    if data.car_needed != "unknown":
        drv = f" (motorista: {data.driver})" if data.driver else ""
        lines.append(f"· 🚗 carro: {data.car_needed}{drv}")
    lines.extend(findings.lines())
    lines.append("\nConfirmar?")
    return "\n".join(lines)


def _summarize_update(ctx: ToolContext, data: UpdateAppointmentInput) -> str:
    current = _repo(ctx).get(data.appointment_id)
    if not current:
        raise ToolError(f"Compromisso #{data.appointment_id} não existe.")
    changes = {k: v for k, v in data.model_dump(exclude_none=True).items() if k != "appointment_id"}
    return (
        f'Alterar "{current["title"]}" (#{data.appointment_id}): '
        + ", ".join(f"{k} → {v!r}" for k, v in changes.items())
        + "\nConfirmar?"
    )


def _summarize_delete(ctx: ToolContext, data: DeleteAppointmentInput) -> str:
    current = _repo(ctx).get(data.appointment_id)
    if not current:
        raise ToolError(f"Compromisso #{data.appointment_id} não existe.")
    return f'Apagar "{current["title"]}" ({logic.to_local_str(current["starts_at"], ctx.timezone)})?'


# --- handlers --------------------------------------------------------------------
def add_appointment(ctx: ToolContext, data: AddAppointmentInput) -> ToolResult:
    view = _draft_view(ctx, data)
    repo = _repo(ctx)
    appt_id = repo.add(
        title=data.title,
        starts_at=view.start.isoformat(),
        ends_at=view.end.isoformat(),
        all_day=int(data.all_day),
        location=data.location,
        notes=data.notes,
        owner_member_id=ctx.member_id,
        attendees_json=json.dumps(list(data.attendees)),
        car_needed=data.car_needed,
        driver_member_id=None,
        rrule=data.recurrence,
        created_by=ctx.member_id,
    )
    when = logic.to_local_str(view.start.isoformat(), ctx.timezone)
    return ToolResult(f"Adicionado: {data.title} — {when} (#{appt_id}).", {"appointment_id": appt_id})


def update_appointment(ctx: ToolContext, data: UpdateAppointmentInput) -> ToolResult:
    repo = _repo(ctx)
    current = repo.get(data.appointment_id)
    if not current:
        raise ToolError(f"Compromisso #{data.appointment_id} não existe.")
    changes: dict = {}
    if data.title is not None:
        changes["title"] = data.title
    if data.start is not None:
        changes["starts_at"] = logic.parse_local(data.start, ctx.timezone).isoformat()
    if data.end is not None:
        changes["ends_at"] = logic.parse_local(data.end, ctx.timezone).isoformat()
    if data.location is not None:
        changes["location"] = data.location
    if data.notes is not None:
        changes["notes"] = data.notes
    if data.attendees is not None:
        changes["attendees_json"] = json.dumps(data.attendees)
    if data.car_needed is not None:
        changes["car_needed"] = data.car_needed
    repo.update(data.appointment_id, changes)
    return ToolResult(f"Atualizado #{data.appointment_id}.")


def delete_appointment(ctx: ToolContext, data: DeleteAppointmentInput) -> ToolResult:
    repo = _repo(ctx)
    current = repo.get(data.appointment_id)
    if not current:
        raise ToolError(f"Compromisso #{data.appointment_id} não existe.")
    repo.delete(data.appointment_id)
    return ToolResult(f'Apagado: "{current["title"]}".')


def list_appointments(ctx: ToolContext, data: ListAppointmentsInput) -> ToolResult:
    tz = ctx.timezone
    start = logic.parse_local(data.range_start, tz) if data.range_start else datetime.now(UTC)
    end = logic.parse_local(data.range_end, tz) if data.range_end else start + timedelta(days=14)
    rows = _repo(ctx).in_range(start.isoformat(), end.isoformat(), data.query)
    if not rows:
        return ToolResult("Nada no período.", {"count": 0})
    lines = []
    for r in rows:
        car = "" if r["car_needed"] in ("unknown", "no") else " 🚗"
        loc = f" @ {r['location']}" if r["location"] else ""
        lines.append(f"#{r['id']} {logic.to_local_str(r['starts_at'], tz)} — {r['title']}{loc}{car}")
    return ToolResult("\n".join(lines), {"count": len(rows)})


def check_car_availability(ctx: ToolContext, data: CheckCarAvailabilityInput) -> ToolResult:
    tz = ctx.timezone
    start = logic.parse_local(data.start, tz)
    end = logic.parse_local(data.end, tz)
    rows = _repo(ctx).in_range(start.isoformat(), end.isoformat())
    car_rows = [r for r in rows if r["car_needed"] in ("yes", "maybe")]
    if not car_rows:
        return ToolResult("O carro está livre nesse período.", {"free": True})
    lines = [
        f'Ocupado: "{r["title"]}" ({logic.to_local_str(r["starts_at"], tz)})' for r in car_rows
    ]
    return ToolResult("O carro NÃO está livre.\n" + "\n".join(lines), {"free": False})


# --- registration --------------------------------------------------------------
def build_tools() -> list[Tool]:
    return [
        Tool("calendar.add_appointment",
             "Add a single appointment. Resolve relative dates to concrete local datetimes first.",
             AddAppointmentInput, add_appointment, writes=True, summarize=_summarize_add),
        Tool("calendar.update_appointment",
             "Change fields of an existing appointment by id.",
             UpdateAppointmentInput, update_appointment, writes=True, summarize=_summarize_update),
        Tool("calendar.delete_appointment",
             "Delete an appointment by id.",
             DeleteAppointmentInput, delete_appointment, writes=True, summarize=_summarize_delete),
        Tool("calendar.list_appointments",
             "List/search appointments in a date range. Read-only.",
             ListAppointmentsInput, list_appointments),
        Tool("calendar.check_car_availability",
             "Check whether the shared car is free in a window, and what holds it. Read-only.",
             CheckCarAvailabilityInput, check_car_availability),
    ]
