from __future__ import annotations

from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    qty: float | None = None
    unit: str | None = None
    category: str | None = None
    needed_by: str | None = Field(None, description="Optional ISO date: buy before this day.")


class AddItemsInput(BaseModel):
    items: list[Item] = Field(..., min_length=1)
    list_name: str = "Supermercado"


class MarkBoughtInput(BaseModel):
    names: list[str] = Field(..., min_length=1)
    list_name: str = "Supermercado"


class RemoveItemsInput(BaseModel):
    names: list[str] = Field(..., min_length=1)
    list_name: str = "Supermercado"


class ShowListInput(BaseModel):
    list_name: str = "Supermercado"
    include_bought: bool = False
