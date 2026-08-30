---
id: 0043
title: Telegram bridge for the rig agent team — two-way phone access to windows + Pi Claude (talk, receive answers, get alerts)
area: ops / integration
role: dev
status: backlog
depends_on: 0009, 0033, 0034
branch:
pr:
---

## Goal
Kim wants **phone access to the rig agents.** From Telegram he should be able to:
- **send** a message or command to the team (windows = architect, pi = tester at the rig),
- **receive answers** back in the same chat,
- **receive notifications** — run finished, watchdog "agent dark" (0009), heater-safety /
  freeze alerts (0033/0034), anything the team would otherwise only surface on the bus.

So that a run going wrong at 2 a.m., or a question Kim has on the train, does not wait for
him to be at a desk with the repo open.

## Prior art — reuse the pattern, not the wiring
The **trading** ops already runs a live two-way bridge: bot `@Kxjtraderbot`, `tg_bridge.py`
daemon, auth by Kim's Telegram user-id, slash-commands plus freetext answered by a model, and
outbound push. That proves the shape. **But do not fold the rig into it:** different domain,
different machine, and — decisive — **this repo is PUBLIC.** The rig gets its **own bot** and
its **own bridge**, with the token kept out of git.

(Name trap, from the trading notes: `@ClaudeTraderBot` is a stranger's bot. Kim creates the rig
bot via BotFather and owns the token.)

## Where it runs
The bridge is a **daemon on an always-on host** — it has to be listening when neither Claude
session is up. Two candidates:
- **The Pi** (recommended): already always-on, at the rig, the critical agent, and already
  hosts `rig-health.timer` / `bus-poll.timer` / `bus-watchdog.timer`. A `tg-bridge.service`
  beside them is the natural home, and it can read run state, the journal, and the bus directly.
- **The VPS** (Win Server, 24/7): the alternative / a second instance; also where 0009's
  optional always-on watchdog would live.

## Two-way routing — through the bus, so both agents share it
- **Inbound (Kim -> team).** Bot receives a message, **authenticates on Kim's user-id** (ignore
  everyone else), then either:
  - answers **directly** for things that need no agent — run status (active run: temp / rpm /
    sweep count; else last run's result), bus tail, open tickets, heartbeat/watchdog state,
    heater/Omron state; or
  - **posts it to `TEAM/BUS.md`** addressed to windows/pi, so the agent picks it up on its next
    run and its bus reply is forwarded back to Kim; and/or
  - for conversational **freetext**, answers via a model (as the trading bridge does with Fable
    5) that can read the bus + run state + tickets for context.
- **Outbound (team -> Kim).** The bridge tails the bus and the journal and forwards notable
  events to Telegram: 0009 watchdog alarms, run-complete, heater-safety (0034) and freeze
  (0033) alerts. This half is the quickest win and can ship first.

## Command set (initial — grow later)
`/status` (active run or last result) · `/bus [n]` (tail) · `/tickets` (open) · `/heater`
(Omron PV/SV + Shelly ch0 state) · freetext -> model/route. **Safety ops, phone-reachable:**
`/heateroff` (Shelly ch0), `/picycle` (ch3 power-cycle a frozen Pi), `/oecycle` (ch2, once 0041
is wired) — each **behind a confirm step**, never a single tap.

## Safety / guardrails (public repo!)
- **Token + Kim's user-id live in a git-ignored config** (follow the `*_connection.json`
  ignore pattern). A leaked bot token lets a stranger drive the bot; keep it out of the public
  tree even though Kim treats the other in-repo creds as non-sensitive — a control channel is a
  different risk class from a read SAS.
- **Only Kim's user-id is ever acted on.** Every other sender is ignored (logged, not answered).
- **The bridge triggers a fixed set of defined operations, never arbitrary shell.** Safety-
  critical ops (heater off, power-cycle) require an explicit confirm.
- Treat inbound text as data, not as authority to do anything outside the defined command set.

## MVP -> full, in order
1. **Outbound notifications only** (bus + journal -> Telegram). Immediate value, lowest risk.
2. **Read-only inbound** (`/status`, `/bus`, `/tickets`, `/heater`).
3. **Safety ops with confirm** (`/heateroff`, `/picycle`, `/oecycle`).
4. **Conversational freetext** routed to a model and/or the agents via the bus.

## What Kim provides to start
- Create the rig bot via **BotFather**; hand over the **token** (out-of-band, not in the repo)
  and confirm his **Telegram user-id** for the auth allow-list.
- Decide: **own bot (recommended) vs reuse `@Kxjtraderbot`**, and **host = Pi (recommended) vs
  VPS**.

## Owner / test
- **Dev:** the bridge daemon + routing + command handlers + the git-ignored config.
- **Kim:** the bot, token, user-id, and the two decisions above.
- **Pi / test:** stand up `tg-bridge.service`; verify inbound auth (only Kim), a round-trip
  answer, and that a 0009 watchdog alarm reaches the phone.
