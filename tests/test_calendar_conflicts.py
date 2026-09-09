"""Conflict checker is pure logic — this is the load-bearing test for the
'notify me about conflicts / car clashes when adding appointments' requirement.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from family_agent.capabilities.calendar.conflicts import (
    ApptView,
    Severity,
    find_findings,
)

UTC = ZoneInfo("UTC")


def at(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def appt(title, start, dur_min=60, car="unknown", location=None, attendees=()):
    return ApptView(
        id=hash(title) & 0xFFFF,
        title=title,
        start=start,
        end=start + timedelta(minutes=dur_min),
        car_needed=car,
        location=location,
        attendees=tuple(attendees),
    )


def test_no_conflict_when_far_apart():
    draft = appt("Dentista", at(2026, 9, 16, 15))
    other = appt("Escola", at(2026, 9, 20, 9))
    fs = find_findings(draft, [other])
    assert fs.findings == []
    assert not fs.has_blocker


def test_hard_time_overlap():
    draft = appt("Dentista", at(2026, 9, 16, 15))
    other = appt("Reunião", at(2026, 9, 16, 14, 30), dur_min=60)
    fs = find_findings(draft, [other])
    assert any(f.severity is Severity.HARD for f in fs.findings)
    assert fs.has_blocker


def test_car_clash_within_travel_buffer_even_without_time_overlap():
    # 15:00-16:00 vs 16:05-17:00 — no time overlap, but < 15 min apart and both need the car
    draft = appt("Dentista", at(2026, 9, 16, 15), car="yes")
    other = appt("Treino", at(2026, 9, 16, 16, 5), car="yes")
    fs = find_findings(draft, [other], travel_buffer_minutes=15)
    assert any(f.severity is Severity.CAR for f in fs.findings)
    assert fs.has_blocker


def test_no_car_clash_when_other_appt_does_not_need_car():
    draft = appt("Dentista", at(2026, 9, 16, 15), car="yes")
    other = appt("Call de casa", at(2026, 9, 16, 15, 30), car="no")
    fs = find_findings(draft, [other])
    assert all(f.severity is not Severity.CAR for f in fs.findings)


def test_tight_turnaround_different_locations():
    draft = appt("Médico", at(2026, 9, 16, 15), location="Centro")
    other = appt("Escola", at(2026, 9, 16, 14), dur_min=55, location="Bairro")
    fs = find_findings(draft, [other], travel_buffer_minutes=15)
    assert any(f.severity is Severity.TURNAROUND for f in fs.findings)
    assert not fs.has_blocker  # a nudge, not a blocker


def test_same_day_info_only():
    draft = appt("Dentista", at(2026, 9, 16, 15))
    other = appt("Compras", at(2026, 9, 16, 10))
    fs = find_findings(draft, [other])
    assert [f.severity for f in fs.findings] == [Severity.INFO]


def test_editing_same_appointment_is_ignored():
    existing = appt("Dentista", at(2026, 9, 16, 15))
    draft = ApptView(id=existing.id, title="Dentista", start=at(2026, 9, 16, 15, 30),
                     end=at(2026, 9, 16, 16, 30))
    fs = find_findings(draft, [existing])
    assert fs.findings == []
