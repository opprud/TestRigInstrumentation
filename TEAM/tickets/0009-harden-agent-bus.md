---
id: 0009
title: Harden the agent bus — heartbeat + watchdog so BUS.md can't go silently deaf
area: ops
role: dev
status: in-review (windows built + self-tested; awaiting Pi-side wiring + kill-poll acceptance)
assignee: unassigned
depends_on:
branch:
pr:
---

## Goal
Make the agent-to-agent channel (`TEAM/BUS.md`) fail **loud**, not silent. If an agent's bus poll
stops, either it self-restarts or a visible alarm is raised — so a message is never silently unread.

## Why
`BUS.md` is the team's async channel; it only works if each agent reliably polls it
(`git fetch` + `git show origin/AutoDetectScope_moj:TEAM/BUS.md`). On **2026-08-19 the Pi agent's
poll stopped by mistake** — the ticket-0007 handoff sat unread until Kim noticed and prompted it.
That is the **same silent-failure class** as the heater guard, the tacho freeze, and the swallowed
VFD start: the system looked fine because nothing raised an error. The bus must not be able to go
deaf without saying so.

## Design (implementer's choice of mechanism)
Core: a **heartbeat + an independent watchdog**.
- **Heartbeat:** each agent stamps its liveness on a cadence (e.g. every 5 min) — a line in
  `TEAM/heartbeats/<agent>.md` (`windows` / `pi`), pushed. Folded into the same poll cycle.
- **Watchdog (independent of the agent session):** something that survives the agent stopping — a
  scheduled task / systemd timer / detached process (the heater-guard detach pattern) — checks the
  *other* side's heartbeat freshness. If it is stale past a threshold (e.g. 2–3× the cadence), raise
  a **visible** alarm: a loud log, a `BUS.md` line from the live side, and/or a push to a human
  channel (e.g. the Telegram bridge if reachable). Optionally attempt to restart the poll.

Key principle (matches the rest of the project): **detect the silence, fail loud.** A dead poll must
surface where a human or the other agent sees it — never just stop.

## Requirements
- Heartbeat cadence + staleness threshold configurable.
- The watchdog must **not** live inside the agent's own poll loop (or it dies with it) — externally
  scheduled / detached.
- The alarm must be visible without a human happening to look (loud log at minimum; a channel ping if available).
- No false alarms during legitimate quiet (threshold ≥ 2–3× cadence).

## Acceptance
- Kill an agent's bus poll → within the threshold an alarm surfaces (log line + bus/channel notice),
  not silence.
- Heartbeats from both agents are visible and fresh during normal operation.
- No alarm during a normal quiet period under the threshold.

## Owner / test
- **Dev:** heartbeat + independent watchdog. **Test:** stop a poll deliberately → confirm the alarm
  fires within the threshold and names which agent went dark.

## Numbering rule (added 2026-08-19, after a live collision)

Pi-Claude and the architect both create tickets, and neither checked the other's numbers first.
The result: **0012 and 0013 were each issued twice for unrelated work** — the architect's RP2040
schematic and Azure archive policy against Pi-Claude's tach calibration and heater-guard retry.
PR #9 carried a title referring to a ticket number that meant something else entirely in the repo.

**The rule:** whoever takes a ticket number announces it on `TEAM/BUS.md` in the same breath as
creating it — number, slug, one line of scope. Announcing costs a sentence; renumbering costs a
file rename, a branch force-push, a PR retitle and a correction to anything that already cited it.

Numbers are never recycled. If a number turns out to be unneeded, leave a short `RESERVED` or
`WITHDRAWN` stub in its place rather than letting the next person claim it — see
`0014-RESERVED.md` for the shape.

This belongs in this ticket because a bus that agents rely on for coordination has to make
collisions *visible*, not merely recoverable. A heartbeat tells you the channel is alive; it does
not tell you two agents just claimed the same name. Worth considering whether the hardening here
should include a check that a new `TEAM/tickets/NNNN-*.md` does not collide on `moj` before it is
committed.

---
## Built 2026-08-30 (windows) — heartbeat + watchdog + collision check

Implemented in Python (stdlib only, runs on Pi + Windows):
- `py/tools/bus_heartbeat.py --agent <name>` — stamps liveness onto a dedicated
  **single parentless commit** on `bus-hb-<name>`, force-pushed, so moj gets ZERO
  heartbeat-commit noise. Folded into the agent's poll cycle (tracks the agent
  polling, not the machine's power).
- `py/tools/bus_watchdog.py --agent <name>` — independent (external scheduler),
  reads the other agents' `bus-hb-*` over `git show`, and on **fresh→stale** appends a
  loud `## … -> ALL` alarm to BUS.md + optional `telegram_cmd`; **stale→fresh** posts a
  recovery line. Alarms once per episode (state in git-ignored
  `py/.bus_watchdog_state.json`). `--dry-run` for testing.
- `py/tools/bus_ticket_check.py <n>` — collision check on origin+local before minting a
  ticket number, suggests the next free one (the cheap half of the numbering rule).
- `py/bus_config.json` (cadence 600 / threshold 1800 = 3×), `docs/Bus_Hardening.md`.

**Self-test passed (windows, 2026-08-30):** heartbeat writes a clean `heartbeat.md`;
watchdog reads FRESH during normal operation; a forged old heartbeat trips the alarm
(dry-run showed the exact BUS.md line); no false alarm under threshold; no state written
in dry-run; all modules compile. Fixed a Windows CRLF-into-`mktree` bug (bytes I/O) and a
cp1252 console crash (UTF-8 reconfigure).

### Remaining for DONE (Pi + scheduling)
- **Pi:** fold `bus_heartbeat.py --agent pi` into its poll cycle; add the watchdog cron
  (see doc). **windows:** heartbeat is folded into the running bus-watch loop; arm the
  Task Scheduler watchdog job (command in the doc) on Kim's nod.
- **Acceptance (Pi):** kill an agent's poll → confirm the other's watchdog raises the
  BUS.md alarm within the threshold and names the dark agent; restart → recovery line.
