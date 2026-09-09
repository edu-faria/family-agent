from __future__ import annotations

from family_agent.capabilities.shopping.logic import ShoppingRepo
from family_agent.capabilities.shopping.schemas import (
    AddItemsInput,
    MarkBoughtInput,
    RemoveItemsInput,
    ShowListInput,
)
from family_agent.tools.registry import Tool, ToolContext, ToolResult


def _repo(ctx: ToolContext) -> ShoppingRepo:
    return ShoppingRepo(ctx.db)


def _summarize_add(ctx: ToolContext, data: AddItemsInput) -> str:
    names = ", ".join(i.name for i in data.items)
    return f"Adicionar à lista **{data.list_name}**: {names}?"


def _summarize_bought(ctx: ToolContext, data: MarkBoughtInput) -> str:
    return f"Marcar como comprado em **{data.list_name}**: {', '.join(data.names)}?"


def _summarize_remove(ctx: ToolContext, data: RemoveItemsInput) -> str:
    return f"Remover de **{data.list_name}**: {', '.join(data.names)}?"


def add_items(ctx: ToolContext, data: AddItemsInput) -> ToolResult:
    repo = _repo(ctx)
    lid = repo.list_id(data.list_name)
    for it in data.items:
        repo.add_item(lid, ctx.member_id, **it.model_dump())
    return ToolResult(f"Adicionei {len(data.items)} item(ns) a {data.list_name}.")


def mark_bought(ctx: ToolContext, data: MarkBoughtInput) -> ToolResult:
    repo = _repo(ctx)
    n = repo.set_status(repo.list_id(data.list_name), data.names, "bought")
    return ToolResult(f"Marcado como comprado: {n} item(ns).")


def remove_items(ctx: ToolContext, data: RemoveItemsInput) -> ToolResult:
    repo = _repo(ctx)
    n = repo.set_status(repo.list_id(data.list_name), data.names, "removed")
    return ToolResult(f"Removido: {n} item(ns).")


def show_list(ctx: ToolContext, data: ShowListInput) -> ToolResult:
    repo = _repo(ctx)
    rows = repo.items(repo.list_id(data.list_name), data.include_bought)
    if not rows:
        return ToolResult(f"A lista {data.list_name} está vazia.", {"count": 0})
    lines = []
    for r in rows:
        qty = f"{r['qty']:g} {r['unit'] or ''}".strip() if r["qty"] else ""
        mark = "✅ " if r["status"] == "bought" else "• "
        lines.append(f"{mark}{r['name']}{(' — ' + qty) if qty else ''}")
    return ToolResult(f"{data.list_name}:\n" + "\n".join(lines), {"count": len(rows)})


def build_tools() -> list[Tool]:
    return [
        Tool("shopping.add_items", "Add one or more items to a shopping list.",
             AddItemsInput, add_items, writes=True, summarize=_summarize_add),
        Tool("shopping.mark_bought", "Mark items as bought.",
             MarkBoughtInput, mark_bought, writes=True, summarize=_summarize_bought),
        Tool("shopping.remove_items", "Remove items from a list.",
             RemoveItemsInput, remove_items, writes=True, summarize=_summarize_remove),
        Tool("shopping.show_list", "Show a shopping list. Read-only.",
             ShowListInput, show_list),
    ]
