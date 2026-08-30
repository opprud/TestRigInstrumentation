# Agent-bus hardening — heartbeat + watchdog (ticket 0009)

The team's async channel is `TEAM/BUS.md` on `AutoDetectScope_moj`. It only works if
each agent (**windows** = architect/merger, **pi** = tester at the rig) reliably polls
it. On 2026-08-19 the Pi's poll stopped by mistake and a ticket handoff sat unread until
a human noticed — the same silent-failure class as the heater guard, the tacho freeze,
and the swallowed VFD start. This makes a dead poll fail **loud**, not silent.

## How it works

Two halves, deliberately on different lifecycles:

1. **Heartbeat — inside the agent's poll cycle.** Every `heartbeat_cadence_sec`, each
   agent runs `bus_heartbeat.py --agent <name>`, which stamps the current UTC time onto
   its own branch `bus-hb-<name>`. It lives in the poll cycle *on purpose*: the heartbeat
   then tracks the **agent actually polling**, not just the machine being powered on. If
   the agent stops polling, the heartbeat stops.

2. **Watchdog — outside the agent, on a scheduler.** Every cadence, an **externally
   scheduled** `bus_watchdog.py --agent <name>` checks the *other* agents' heartbeats. If
   one is older than `stale_threshold_sec`, it fails loud. It must NOT run inside the poll
   loop, or it would die with the very thing it is supposed to watch.

So `windows` heartbeats from its session and its watchdog (a Task Scheduler job) watches
`pi`; `pi` heartbeats from its session and its watchdog (a cron job) watches `windows`.
Each side's watchdog survives its own agent dying and reports the *other* going dark.

### Why heartbeats are on their own branches
Stamping liveness every few minutes onto `moj` would bury real history under hundreds of
commits a day. Instead each heartbeat is a single **parentless** commit force-pushed to
`bus-hb-<agent>`, so that branch never grows and `moj` stays clean. The watchdog reads it
with `git fetch` + `git show origin/bus-hb-<other>:heartbeat.md` — never a checkout, so it
does not disturb a working tree mid-run.

### The alarm
When an agent goes stale the watchdog:
- always writes a line to `py/bus_watchdog.log` (git-ignored),
- on the **fresh→stale** edge appends a loud `## … <me> -> ALL` line to `TEAM/BUS.md` and
  pushes it, naming the dark agent, and runs the optional `telegram_cmd`,
- on the **stale→fresh** edge appends a recovery line.

A standing outage is announced **once** (state in `py/.bus_watchdog_state.json`,
git-ignored), never every tick, so a genuinely long outage does not spam the bus.

## Config — `py/bus_config.json`
| key | meaning |
|---|---|
| `branch` | the bus branch (`AutoDetectScope_moj`) |
| `agents` | agent names; each needs a `bus-hb-<name>` heartbeat |
| `heartbeat_cadence_sec` | how often each agent stamps (default 600) |
| `stale_threshold_sec` | watchdog alarms past this age; keep ≥ 2–3× cadence (default 1800) |
| `telegram_cmd` | optional shell command on alarm, `{msg}` substituted; `null` = none |

No false alarms during a legitimate quiet stretch: the threshold is 3× the cadence, and
the heartbeat fires on liveness, not on bus traffic.

## Scheduling

**windows (this machine) — heartbeat** is folded into the poll loop (the scratchpad
`bus_watch3.sh` calls `bus_heartbeat.py --agent windows` every cadence). **watchdog** as a
Task Scheduler job, independent of the Claude session:
```
schtasks /Create /TN "RigBusWatchdog" /SC MINUTE /MO 10 ^
  /TR "py -3 \"Z:\Projects\AaU\software\sandbox\TestRigInstrumentation\py\tools\bus_watchdog.py\" --agent windows" /F
```

**pi — heartbeat** folded into its poll cycle; **watchdog** as cron (survives the agent):
```
*/10 * * * * cd /home/pi/TestRigInstrumentation && \
  /usr/bin/python3 py/tools/bus_watchdog.py --agent pi >> py/bus_watchdog.log 2>&1
```

## Acceptance test (ticket 0009)
1. Both agents heartbeating: `python3 py/tools/bus_watchdog.py --agent windows` (and
   `--agent pi`) logs the other as **fresh** during normal operation.
2. **Kill a poll:** stop one agent's heartbeat. Within `stale_threshold_sec` the other
   agent's watchdog appends a `BUS WATCHDOG: <agent> has gone dark` line and (if wired)
   pings the channel — **not** silence. `--dry-run` shows the alarm without pushing.
3. **No false alarm:** during a normal quiet stretch under the threshold, the watchdog
   logs `fresh` and does nothing.
4. Restart the poll → within a cadence a `back` recovery line appears.

## Bonus — ticket-number collisions
`bus_ticket_check.py <n>` checks a number against `origin/<branch>` and the working tree
before you mint `TEAM/tickets/<n>-*.md`, and suggests the next free number — the cheap
half of the 0009 numbering rule (announce the number on the bus as you take it). Prompted
by the real 0011 double-claim on 2026-08-30.
