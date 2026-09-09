"""Conflict & relevance detection for a proposed appointment.

Pure logic, no DB — unit-tested in tests/test_calendar_conflicts.py. The calendar
tools call `find_findings()` before proposing any add/move, and every finding is
put into the confirmation message the family sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

CAR_NEEDS = {"yes", "maybe"}


class Severity(str, Enum):
    HARD = "hard"          # times overlap
    CAR = "car"            # both need the shared car in the same window
    TURNAROUND = "turnaround"  # too little travel time between two appointments
    INFO = "info"         # same day / same attendee — not a conflict, just context


@dataclass(frozen=True)
class ApptView:
    """Minimal view of an appointment for conflict math. Times are timezone-aware UTC."""

    id: int | None
    title: str
    start: datetime
    end: datetime
    car_needed: str = "unknown"
    location: str | None = None
    attendees: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    severity: Severity
    message: str
    other_id: int | None = None
    other_title: str = ""


@dataclass
class FindingSet:
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_blocker(self) -> bool:
        return any(f.severity in (Severity.HARD, Severity.CAR) for f in self.findings)

    def lines(self) -> list[str]:
        icon = {
            Severity.HARD: "⛔",
            Severity.CAR: "🚗",
            Severity.TURNAROUND: "⏱️",
            Severity.INFO: "ℹ️",
        }
        return [f"{icon[f.severity]} {f.message}" for f in self.findings]


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _shared(a: ApptView, b: ApptView) -> bool:
    return bool(set(x.lower() for x in a.attendees) & set(x.lower() for x in b.attendees))


def find_findings(
    draft: ApptView,
    existing: list[ApptView],
    travel_buffer_minutes: int = 15,
) -> FindingSet:
    buf = timedelta(minutes=max(0, travel_buffer_minutes))
    out: list[Finding] = []

    for ex in existing:
        if ex.id is not None and ex.id == draft.id:
            continue  # editing the same appointment

        time_overlap = _overlaps(draft.start, draft.end, ex.start, ex.end)
        window_overlap = _overlaps(
            draft.start - buf, draft.end + buf, ex.start - buf, ex.end + buf
        )

        if time_overlap:
            who = " (mesma pessoa)" if _shared(draft, ex) else ""
            out.append(Finding(
                Severity.HARD,
                f'Sobreposição com "{ex.title}" ({_fmt(ex.start)}–{_fmt(ex.end)}){who}.',
                ex.id, ex.title,
            ))

        if (
            draft.car_needed in CAR_NEEDS
            and ex.car_needed in CAR_NEEDS
            and window_overlap
        ):
            out.append(Finding(
                Severity.CAR,
                f'O carro já está reservado para "{ex.title}" ({_fmt(ex.start)}–{_fmt(ex.end)}).',
                ex.id, ex.title,
            ))

        if (
            not time_overlap
            and window_overlap
            and draft.location
            and ex.location
            and draft.location.strip().lower() != ex.location.strip().lower()
        ):
            out.append(Finding(
                Severity.TURNAROUND,
                f'Pouco tempo entre "{ex.title}" ({ex.location}) e este ({draft.location}).',
                ex.id, ex.title,
            ))

        if not window_overlap and ex.start.date() == draft.start.date():
            out.append(Finding(
                Severity.INFO,
                f'No mesmo dia: "{ex.title}" às {_fmt(ex.start)}.',
                ex.id, ex.title,
            ))

    # de-dup + stable order by severity
    order = {Severity.HARD: 0, Severity.CAR: 1, Severity.TURNAROUND: 2, Severity.INFO: 3}
    seen: set[tuple] = set()
    deduped: list[Finding] = []
    for f in sorted(out, key=lambda f: order[f.severity]):
        key = (f.severity, f.other_id, f.message)
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return FindingSet(deduped)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m %H:%M")
