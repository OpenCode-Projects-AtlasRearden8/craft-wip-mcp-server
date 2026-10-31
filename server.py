#!/usr/bin/env python3
"""craft-wip-mcp-server: a tiny stdio MCP server for the craft room.

Pure Python stdlib. Speaks JSON-RPC 2.0 over stdin/stdout using
newline-delimited JSON (the MCP stdio transport). Tools manage:

- works in progress (pattern notes + progress counters)
- stash materials (quantities + dye lots)
- gift deadlines with lead-time nudges
- finish-first planning (what can actually be done next)

Data lives in a local JSON file (CRAFT_ROOM_DATA, default data/craft-store.json)
with path safety and timestamped auto-backups. Offline, local-first, no
network. Made by Asdale Dynamics, LLC.

Smallest test-friendly shape: every request is dispatched through
`handle_message`, which is a pure function of (message, server state).
"""

from __future__ import annotations

import json
import os
import sys
import datetime
import pathlib
from typing import Any

import craftlib
from craftlib import CraftError
import craft_samples

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "craft-wip-mcp-server"
SERVER_VERSION = "1.0.0"
DEFAULT_DATA_DIR = "data"
DEFAULT_DATA_FILE = "craft-store.json"


def data_file_from_env() -> pathlib.Path:
    """Resolve the data file with path safety against the data directory."""
    base = pathlib.Path(
        os.environ.get("CRAFT_ROOM_DATA", DEFAULT_DATA_DIR)
    ).expanduser()
    fname = os.environ.get("CRAFT_ROOM_FILE", DEFAULT_DATA_FILE)
    return craftlib.safe_path(base, fname)


# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------

class Server:
    """Holds the data file path and the loaded store."""

    def __init__(self, data_file: pathlib.Path | None = None, seed: bool = True):
        self.data_file = data_file if data_file is not None else data_file_from_env()
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.store = self._load()

    def _load(self) -> dict[str, Any]:
        store = craftlib.load_store(self.data_file)
        if self.seed and not store.get("wips") and not store.get("stash"):
            store = craft_samples.sample_store()
            craftlib.save_store(self.data_file, store)
        return store

    def save(self) -> None:
        craftlib.save_store(self.data_file, self.store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_id(items: list[dict[str, Any]], prefix: str) -> str:
    nums = []
    for it in items:
        try:
            nums.append(int(str(it.get("id", "")).split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{max(nums, default=0) + 1}"


def _find(items: list[dict[str, Any]], item_id: str, kind: str) -> dict[str, Any]:
    hits = [i for i in items if i.get("id") == item_id]
    if not hits:
        raise CraftError(f"no {kind} with id {item_id!r} (try list_{kind}s)")
    return hits[0]


def _today() -> datetime.date:
    return craftlib.utc_today()


# ---------------------------------------------------------------------------
# Tool implementations (each returns a plain value for JSON serialization)
# ---------------------------------------------------------------------------

def tool_add_wip(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        raise CraftError("name is required")
    total = craftlib._int_in_range(args.get("total_units"), 0, "total_units")
    done = craftlib._int_in_range(args.get("done_units", 0), 0, "done_units")
    if done > total:
        raise CraftError("done_units cannot exceed total_units")
    needs = _normalize_needs(args.get("needs"))
    wip = {
        "id": _next_id(server.store["wips"], "w"),
        "name": name,
        "craft_type": str(args.get("craft_type") or "other"),
        "pattern_notes": str(args.get("pattern_notes") or ""),
        "total_units": total,
        "done_units": done,
        "needs": needs,
        "deadlines": [],
    }
    server.store["wips"].append(wip)
    server.save()
    return wip


def _normalize_needs(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise CraftError("needs must be a list of {name, per_unit}")
    out = []
    for n in raw:
        if not isinstance(n, dict) or not str(n.get("name") or "").strip():
            raise CraftError("each need needs a material name")
        per = n.get("per_unit", 0)
        if isinstance(per, bool) or not isinstance(per, (int, float)) or per <= 0 or per > 1_000_000:
            raise CraftError("per_unit must be a positive number")
        out.append({"name": str(n["name"]).strip(), "per_unit": per})
    return out


def tool_update_progress(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    wip = _find(server.store["wips"], str(args.get("wip_id") or ""), "wip")
    total = wip["total_units"]
    if "add_units" in args and "set_done" in args:
        raise CraftError("use either add_units or set_done, not both")
    if "add_units" in args:
        add = craftlib._int_in_range(args["add_units"], -total, "add_units")
        done = wip["done_units"] + add
    elif "set_done" in args:
        done = craftlib._int_in_range(args["set_done"], 0, "set_done")
    else:
        raise CraftError("provide add_units or set_done")
    if done < 0:
        raise CraftError("progress cannot go below 0")
    if done > total:
        raise CraftError(f"total_units is {total}; raise odds before done exceeds it")
    wip["done_units"] = done
    server.save()
    return {
        "id": wip["id"],
        "name": wip["name"],
        "done_units": done,
        "total_units": total,
        "progress_pct": craftlib.progress_pct(done, total),
    }


def tool_list_wips(server: Server, _args: dict[str, Any]) -> list[dict[str, Any]]:
    today = _today()
    out = []
    for w in server.store["wips"]:
        out.append(
            {
                "id": w["id"],
                "name": w["name"],
                "craft_type": w.get("craft_type"),
                "done_units": w.get("done_units"),
                "total_units": w.get("total_units"),
                "progress_pct": craftlib.progress_pct(w.get("done_units", 0), w.get("total_units", 0)),
                "pattern_notes": w.get("pattern_notes"),
                "needs": w.get("needs", []),
                "deadlines": w.get("deadlines", []),
                "days_to_deadline": craftlib.min_days_left(w, today),
            }
        )
    out.sort(key=lambda x: x["id"])
    return out


def tool_get_wip(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    w = _find(server.store["wips"], str(args.get("wip_id") or ""), "wip")
    return w


def tool_log_stash(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    material = str(args.get("material") or "").strip().lower()
    if not material:
        raise CraftError("material is required")
    qty = _positive_number(args.get("quantity"), "quantity")
    unit = str(args.get("unit") or "units").strip()
    item = {
        "id": _next_id(server.store["stash"], "s"),
        "material": material,
        "quantity": qty,
        "unit": unit,
        "dye_lot": str(args.get("dye_lot") or "").strip(),
        "note": str(args.get("note") or ""),
    }
    server.store["stash"].append(item)
    server.save()
    return item


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 or value > 1_000_000:
        raise CraftError(f"{name} must be a positive number")
    return value


def tool_use_stash(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    qty = _positive_number(args.get("quantity"), "quantity")
    stash_id = args.get("stash_id")
    if stash_id:
        item = _find(server.store["stash"], str(stash_id), "stash item")
    else:
        material = str(args.get("material") or "").strip().lower()
        hits = [s for s in server.store["stash"] if s["material"] == material]
        if not hits:
            raise CraftError(f"no stash item for material {material!r}")
        item = hits[0]
    if qty > (item["quantity"] or 0):
        raise CraftError(f"only {item['quantity']} {item['unit']} of {item['material']!r} in stash")
    item["quantity"] = round(item["quantity"] - qty, 4)
    server.save()
    return item


def tool_list_stash(server: Server, _args: dict[str, Any]) -> list[dict[str, Any]]:
    out = sorted(server.store["stash"], key=lambda s: (s["material"], s.get("dye_lot") or ""))
    return [
        {
            "id": s["id"],
            "material": s["material"],
            "quantity": s["quantity"],
            "unit": s["unit"],
            "dye_lot": s.get("dye_lot") or "",
            "note": s.get("note") or "",
        }
        for s in out
    ]


def tool_add_gift_deadline(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    wip = _find(server.store["wips"], str(args.get("wip_id") or ""), "wip")
    recipient = str(args.get("recipient") or "").strip()
    if not recipient:
        raise CraftError("recipient is required (who gets the gift?)")
    date_str = str(args.get("event_date") or "").strip()
    craftlib.days_until(date_str)  # validates format
    lead = craftlib._int_in_range(args.get("lead_time_days", 14), 1, "lead_time_days")
    deadline = {
        "id": _next_id(wip["deadlines"], "d"),
        "recipient": recipient,
        "event_date": date_str,
        "lead_time_days": lead,
    }
    wip["deadlines"].append(deadline)
    server.save()
    return _view_deadline(wip, deadline)


def _view_deadline(wip: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    today = _today()
    days = craftlib.days_until(d["event_date"], today)
    return {
        "wip_id": wip["id"],
        "wip_name": wip["name"],
        "deadline_id": d["id"],
        "recipient": d["recipient"],
        "event_date": d["event_date"],
        "days_left": days,
        "lead_time_days": d["lead_time_days"],
        "nudge": craftlib.lead_time_nudge(days, d["lead_time_days"]),
    }


def tool_list_deadlines(server: Server, _args: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for w in server.store["wips"]:
        for d in w["deadlines"]:
            out.append(_view_deadline(w, d))
    out.sort(key=lambda x: x["event_date"])
    return out


def tool_finish_first(server: Server, args: dict[str, Any]) -> dict[str, Any]:
    limit_raw = args.get("limit", 3)
    if isinstance(limit_raw, bool) or not isinstance(limit_raw, int) or limit_raw < 1 or limit_raw > 50:
        raise CraftError("limit must be an integer between 1 and 50")
    ranked = craftlib.rank_wips(server.store["wips"], server.store["stash"], _today())
    return {
        "what_to_pick_up_next": ranked[:limit_raw],
        "hint": "The top row is your best bet to actually finish soon.",
    }


TOOL_FUNCS = {
    "add_wip": tool_add_wip,
    "update_progress": tool_update_progress,
    "list_wips": tool_list_wips,
    "get_wip": tool_get_wip,
    "log_stash": tool_log_stash,
    "use_stash": tool_use_stash,
    "list_stash": tool_list_stash,
    "add_gift_deadline": tool_add_gift_deadline,
    "list_deadlines": tool_list_deadlines,
    "finish_first": tool_finish_first,
}


def tool_schemas() -> list[dict[str, Any]]:
    def sch(
        name: str,
        description: str,
        **props: Any,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": props.get("properties", {}),
                "required": props.get("required", []),
            },
        }

    num = {"type": "number"}
    return [
        sch(
            "add_wip",
            "Add a work in progress. Give its size in countable units (rows, stitches, charms), plus pattern notes and any materials it eats.",
            properties={
                "name": {"type": "string"},
                "craft_type": {"type": "string"},
                "pattern_notes": {"type": "string"},
                "total_units": {"type": "integer", "minimum": 0},
                "done_units": {"type": "integer", "minimum": 0},
                "needs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "per_unit": num},
                        "required": ["name", "per_unit"],
                    },
                },
            },
            required=["name", "total_units"],
        ),
        sch(
            "update_progress",
            "Bump or set progress on a WIP. Use add_units for 'finished 5 more rows' or set_done to set absolute progress.",
            properties={
                "wip_id": {"type": "string"},
                "add_units": {"type": "integer"},
                "set_done": {"type": "integer", "minimum": 0},
            },
            required=["wip_id"],
        ),
        sch(
            "list_wips",
            "List every work in progress with progress %, raw counters, notes, needs and deadlines.",
        ),
        sch(
            "get_wip",
            "Full detail for one work in progress.",
            properties={"wip_id": {"type": "string"}},
            required=["wip_id"],
        ),
        sch(
            "log_stash",
            "Log a stash purchase: material name, quantity, unit, dye lot, note.",
            properties={
                "material": {"type": "string"},
                "quantity": num,
                "unit": {"type": "string"},
                "dye_lot": {"type": "string"},
                "note": {"type": "string"},
            },
            required=["material", "quantity"],
        ),
        sch(
            "use_stash",
            "Consume quantity from the stash (by stash_id, or by material name taking the first match).",
            properties={
                "stash_id": {"type": "string"},
                "material": {"type": "string"},
                "quantity": num,
            },
            required=["quantity"],
        ),
        sch(
            "list_stash",
            "List the stash: quantities, units and dye lots, sorted by material.",
        ),
        sch(
            "add_gift_deadline",
            "Attach a gift deadline to a WIP (recipient, event date, lead time in days) so nudges fire in time.",
            properties={
                "wip_id": {"type": "string"},
                "recipient": {"type": "string"},
                "event_date": {"type": "string", "description": "ISO YYYY-MM-DD"},
                "lead_time_days": {"type": "integer", "minimum": 1},
            },
            required=["wip_id", "recipient", "event_date"],
        ),
        sch(
            "list_deadlines",
            "All gift deadlines sorted by date, with days left and the lead-time nudge.",
        ),
        sch(
            "finish_first",
            "Rank WIPs by a 'how likely is this to actually get finished' score: progress, deadline urgency, and missing materials.",
            properties={"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        ),
    ]


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------

def _tool_error(msg: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": msg}],
        "isError": True,
    }


def _tool_ok(value: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, indent=2)}],
        "isError": False,
    }


def handle_message(msg: Any, server: Server) -> dict[str, Any] | None:
    """Handle one decoded JSON-RPC message. Returns the response or None."""
    if not isinstance(msg, dict):
        return _rpc_error(None, -32600, "not a JSON-RPC object")
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tool_schemas()},
        }
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        func = TOOL_FUNCS.get(name) if isinstance(name, str) else None
        if func is None:
            return _rpc_error(msg_id, -32602, f"unknown tool: {name!r}")
        args = params.get("arguments") or {}
        try:
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_ok(func(server, args))}
        except CraftError as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_error(str(exc))}
        except Exception as exc:  # noqa: BLE001 - keep server alive, report
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _tool_error(f"internal error: {exc}"),
            }
    return _rpc_error(msg_id, -32601, f"method not found: {method!r}")


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id if isinstance(msg_id, (str, int)) and msg_id is not None else None,
        "error": {"code": code, "message": message},
    }


def main() -> None:
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = _rpc_error(None, -32600, "invalid JSON")
        else:
            resp = handle_message(msg, server)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
