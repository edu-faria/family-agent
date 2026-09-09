"""Pydantic input models for the calendar tools. These become the JSON schemas
the LLM sees, and the dispatcher validates every call against them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CarNeeded = Literal["yes", "no", "maybe", "unknown"]


class AddAppointmentInput(BaseModel):
    title: str = Field(..., description="Short title, e.g. 'Dentista (Lena)'.")
    start: str = Field(..., description="Local start, ISO-8601 with offset or 'YYYY-MM-DD HH:MM'. "
                                       "Resolve relative dates to a concrete local datetime first.")
    end: str | None = Field(None, description="Local end. Omit to default to start + 1 hour.")
    all_day: bool = False
    location: str | None = None
    notes: str | None = None
    attendees: list[str] = Field(default_factory=list, description="Family member names involved.")
    car_needed: CarNeeded = Field("unknown", description="Whether the shared family car is needed.")
    driver: str | None = Field(None, description="Who drives, if the car is needed.")
    recurrence: str | None = Field(None, description="Optional RRULE string, e.g. 'FREQ=WEEKLY'.")


class UpdateAppointmentInput(BaseModel):
    appointment_id: int
    title: str | None = None
    start: str | None = None
    end: str | None = None
    location: str | None = None
    notes: str | None = None
    attendees: list[str] | None = None
    car_needed: CarNeeded | None = None
    driver: str | None = None


class DeleteAppointmentInput(BaseModel):
    appointment_id: int


class ListAppointmentsInput(BaseModel):
    range_start: str | None = Field(None, description="Local datetime lower bound. Default: now.")
    range_end: str | None = Field(None, description="Local datetime upper bound. Default: +14 days.")
    query: str | None = Field(None, description="Optional text filter on title/location/notes.")


class CheckCarAvailabilityInput(BaseModel):
    start: str = Field(..., description="Local datetime.")
    end: str = Field(..., description="Local datetime.")
