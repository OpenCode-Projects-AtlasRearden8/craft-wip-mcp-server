# STATUS - craft-wip-mcp-server

Built and verified on 2026-10-31 by Asdale Dynamics, LLC.

## What was built

A zero-dependency MCP server (Python 3 stdlib) over the MCP stdio transport
(newline-delimited JSON-RPC 2.0) for tracking the craft room:

- **10 tools**: `add_wip`, `update_progress`, `list_wips`, `get_wip`,
  `log_stash`, `use_stash`, `list_stash`, `add_gift_deadline`,
  `list_deadlines`, `finish_first`
- **Works in progress** with pattern notes, countable units (rows/stitches/
  charms), done counters, and material needs (`{name, per_unit}`)
- **Stash logging** with quantities, units, and dye lots; `use_stash` refuses
  to overspend what's on hand
- **Gift deadlines** with lead-time nudges: overdue / due today / start now /
  nudge / on track / plenty of time
- **finish_first ranking**: score = 55% progress + 30% deadline urgency +
  15% unblocked-materials; top row is what to pick up next
- **JSON storage** (`data/craft-store.json`) with:
  - path safety (traversal, absolute-path, null-byte, symlink escapes rejected)
  - atomic writes (temp file + `os.replace`)
  - auto-backups to `data/backups/`, newest 5 kept
- **Sample projects** auto-seeded on first run (3 WIPs, 4 stash items, 2
  deadlines) so the room is never empty on day one

Files: `server.py` (MCP dispatch + tools), `craftlib.py` (storage, path
safety, math), `craft_samples.py` (seed data), `tests/`, `README.md`,
`LICENSE` (MIT, Copyright (c) 2026 Asdale Dynamics, LLC).

## How to run

```bash
python3 server.py
```

Data file override: `CRAFT_ROOM_DATA=/some/dir CRAFT_ROOM_FILE=store.json`.
Run from the project directory if using the default `data/` path.

## Verification results

- `python3 -m unittest discover -s tests -v` -> **52 tests, OK** (0.02s):
  - progress math: rounding, zero-total marker, negative/type rejection
  - deadline math: same-day 0, overdue negatives, leap-day, month rollover,
    nudge bands, short lead times
  - finish-first: progress ranking, blocked-by-material handling, fake-today seam
  - security: `../../etc/passwd` traversal, absolute escapes, null bytes,
    symlink escapes, non-container backup dirs, SQL/injection-style strings
    stored safely as data
  - storage: round-trip, auto-backup creation + 5-file retention, corrupt and
    wrong-shape JSON rejected, no leftover temp files
  - server: initialize handshake, tools/list schema, notifications silent,
    unknown tool/method errors, tool error surfacing, seeded sample store
- Manual stdio smoke test (initialize + tools/list + finish_first +
  update_progress) produced correct responses in one pass.
- Protocol response to `initialize` advertises MCP protocol `2024-11-05`.

## Known gaps

- One deadline per tool call; recipients get one WIP each by design.
- Material matching is case-insensitive name equality against the *first*
  need entry only - multi-material blocking is future work.
- Backup timestamps use wall-clock datetime; two saves within the same
  microsecond could share a name (add a sequence number if that matters).
- MCP `resources`/`prompts` capabilities are not implemented; tools only.
- No CRLF framing variant of the stdio transport (newline-delimited only,
  which is what most clients send).
- Tests patch date behavior through the `craftlib.utc_today` seam rather than
  freezing the system clock.
