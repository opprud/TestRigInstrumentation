---
id: 0009
title: Harden the agent bus — heartbeat + watchdog so BUS.md can't go silently deaf
area: ops
role: dev
status: backlog
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
