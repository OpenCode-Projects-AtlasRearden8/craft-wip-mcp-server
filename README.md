# craft-wip-mcp-server

A tiny MCP server for the craft room, written in pure Python (standard library
only, zero dependencies). It tracks your actual, honest crafting reality:

- **Works in progress** with pattern notes and progress counters
  ("60 rows done of 180", not vibes)
- **Stash materials** with quantities and dye lots, so you know whether the
  cranberry yarn can actually survive the whole scarf
- **Gift deadlines** with lead-time nudges, so projects start in time to
  land on time
- **finish_first**, a ranked answer to "what could I actually finish next?"
  balancing progress, deadline urgency, and missing materials

Built by [Asdale Dynamics, LLC](https://dylanasdale.github.io) - plain-English
AI tools, step by step, never condescending. This server is deliberately
distinct from `craft-fair-seller-handbook` (selling) and
`gift-stash-mcp-server` (gift inventory): this one is about *the making*.

Runs fully offline. Data lives in a local JSON file with timestamped
auto-backups and strict path-safety checks.

## How to run it

```bash
python3 server.py
```

That's it. The server speaks the MCP stdio transport (newline-delimited
JSON-RPC 2.0) on stdin/stdout, so any MCP client - Claude Desktop, other
agent tools, or hand-rolled scripts - can drive it.

Smoke test it by hand, no client needed:

```bash
printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_wips","arguments":{}}}' \
  | python3 server.py
```

A freshly started server seeds itself with friendly sample projects
(three WIPs, a small stash with dye lots) so the room is never empty. Delete
`data/craft-store.json` to reset to samples again.

### MCP client config

Add to your client's MCP server list:

```json
{
  "mcpServers": {
    "craft-wip": {
      "command": "python3",
      "args": ["/path/to/craft-wip-mcp-server/server.py"]
    }
  }
}
```

### Environment knobs

| Variable           | Default        | Meaning                       |
| ------------------ | -------------- | ----------------------------- |
| `CRAFT_ROOM_DATA`  | `data/`        | Base directory for the store  |
| `CRAFT_ROOM_FILE`  | `craft-store.json` | File name inside the base |

Both are resolved with path-safety checks; any path escaping the base
directory (traversal, absolute overrides, symlink hops, null bytes) is
rejected. Auto-backups go to `<data dir>/backups/`, keeping the newest 5.

## The tools

| Tool                                                        | What it does |
| ----------------------------------------------------------- | ------------ |
| `add_wip` (name, total_units, pattern_notes?, needs?)        | Add a project with countable units (rows, stitches, charms) |
| `update_progress` (wip_id, add_units \| set_done)            | "Finished 5 more rows", or set absolute progress |
| `list_wips` / `get_wip`                                     | Progress %, counters, notes, needs, deadlines |
| `log_stash` (material, quantity, unit, dye_lot?)             | Log stash purchases with dye lots |
| `use_stash` (quantity, stash_id? \| material?)               | Pull from the stash; refuses to overspend |
| `list_stash`                                                | Quantities, units, dye lots, sorted |
| `add_gift_deadline` (wip_id, recipient, event_date, lead_time_days?) | Deadline + nudge math ("start now - critically close") |
| `list_deadlines`                                            | All deadlines, days left, nudges |
| `finish_first` (limit?)                                     | Ranked: what can actually be finished next |

`finish_first` scores each WIP as a mix of progress (55%), deadline urgency
(30%), and a blocked-by-materials penalty (15%). The top row is the one to
pick up next.

## Tests

Fully offline, stdlib `unittest` only:

```bash
python3 -m unittest discover -s tests -v
```

Covers progress math, deadline/leap-day edge cases, nudge bands,
finish-first ranking, storage round-trips, auto-backup retention, corrupt
JSON rejection, and security cases (path traversal, symlinks, absolute-path
escapes, null bytes, injection-style strings stored harmlessly as data).

## License

MIT - Copyright (c) 2026 Asdale Dynamics, LLC. See [LICENSE](LICENSE).
