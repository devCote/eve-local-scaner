"""EFT export for the native zKill fitting popup."""

from __future__ import annotations

from typing import Any

from zkill_fit_utils import safe_int


def build_eft_fit_text(fit_data: dict[str, Any], row_data: dict[str, Any]) -> str:
    ship_name = str(fit_data.get("ship_name") or row_data.get("ship_name") or "Ship")
    items = fit_data.get("items") if isinstance(fit_data.get("items"), dict) else {}
    type_names = fit_data.get("type_names") if isinstance(fit_data.get("type_names"), dict) else {}

    def name_for(type_id: int) -> str:
        return str(type_names.get(int(type_id), f"Type {int(type_id)}"))

    lines: list[str] = [f"[{ship_name}, zKill Fit]", ""]

    for slot in ("low", "mid", "high"):
        slot_items = list(items.get(slot) or [])
        slot_items.sort(key=lambda row: int(row.get("slot_index") or 0))
        for row in slot_items:
            lines.append(name_for(safe_int(row.get("type_id"))))
        lines.append("")

    for slot in ("rig", "subsystem"):
        slot_items = list(items.get(slot) or [])
        slot_items.sort(key=lambda row: int(row.get("slot_index") or 0))
        for row in slot_items:
            lines.append(name_for(safe_int(row.get("type_id"))))
        if slot_items:
            lines.append("")

    charges: list[str] = []
    for slot in ("high", "mid", "low"):
        for row in list(items.get(slot) or []):
            charge_id = safe_int(row.get("charge_type_id"))
            if charge_id:
                charges.append(name_for(charge_id))
    if charges:
        for charge_name in charges:
            lines.append(f"{charge_name} x1")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
