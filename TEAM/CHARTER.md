# TestRig Dev Team — Charter (v0, living)

Owned by Kim (customer) + the architect. Everything here is provisional and evolves via PR.

## Who
- **Customer** — Kim (owner). Final say; can implement anything directly at any time.
- **Customer proxy / architect** — Claude on Kim's Windows machine. Turns Kim's wishes into tickets, guards the architecture, reports status back to Kim.
- **PM** (VPS) — owns the integration branch, triages/assigns tickets, reviews + merges PRs, reports.
- **Developers** (VPS):
  - **firmware** — `firmware/` (RP2040)
  - **acquisition + control** — `py/acquire_scope_data.py`, scope, modbus, motor
  - **BLE + dashboard** — `BearingBrain/`, `py/` BLE, `react/`
- **Tester** (Pi) — owns the rig hardware; runs PRs on real hardware; reports results. **Must confirm the rig is free (no live run) before testing.**
- **QA / Docs** (VPS) — keeps `CLAUDE.md` + docs in sync; reviews PRs for doc completeness.

## Where
- **Pi** — tester + the live rig control (kept lean; dev work must never starve it).
- **VPS** — PM, devs, QA (the "office"). **Isolated from the live-trading systems on the same box.**
- **Windows** — customer proxy.

## Coordination
- **Git/GitHub = source of truth.** Integration branch: `AutoDetectScope_moj`. One ticket → one feature branch → one PR, reviewed + merged by PM. Repo: `opprud/TestRigInstrumentation`.
- **AgentHub bus (VPS) = real-time coordination/nudges** ("PR #N ready", "rig free now", dispatch). Off-VPS agents (Pi, Windows) join via the `hub_relay.py` relay (NordVPN/tailnet workaround).
- **Gated mutations** (same discipline as *"the hub stores text, never trades"*): no agent mutates code or flashes hardware **directly via the bus**. Code lands only through PR merge (PM); hardware runs only through the tester with a rig-free check.

## Ways of working
- **Pull first, always** — `git fetch` + `git pull --ff-only` on `AutoDetectScope_moj` before any work.
- **Tickets** — `TEAM/tickets/NNNN-slug.md` with frontmatter (`status`, `area`, `assignee`, `branch`, `pr`). Status flow: `backlog → assigned → in-progress → review → hw-test → done`. *(Graduate to GitHub Issues once `gh` is installed.)*
- **Small PRs.** PR description links its ticket. Firmware/hardware-affecting PRs get a `hw-test` step: tester runs on the rig when free and reports on the PR before merge.
- **Docs travel with code** — any behavior/interface change updates `CLAUDE.md` in the same PR; QA verifies.
- **Never re-flash the RP2040 while a test runs.** Never push disruptive changes while the Pi runs a live test.

## Prerequisite before any VPS dev-agent runs
Isolate the dev team from live trading on the VPS: own user/dir, **no access** to trading code / MT5 / broker `.env`; a GitHub credential scoped **only** to this repo.
