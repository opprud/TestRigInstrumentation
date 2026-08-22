---
id: 0029
title: Scope connection stability — 114 wedge/recovery cycles in the 13 h run, ConnectionRefused-dominated
area: acquisition
role: dev
status: backlog
assignee: unassigned
depends_on:
branch:
pr:
---

## Problem
The scope's TCP/LXI connection is intermittently **refused** or times out throughout a long run. The
retry machinery recovers almost all of it, so it is nearly invisible in the data — but it is
frequent, and the run is one un-recovered retry away from losing a sweep (it lost exactly one).

## Evidence — 13 h run `20260820_125647` (`acquire_scope.log`)
- **468 error lines**, **114 "resetting scope" wedge/recovery cycles** over 13 h — roughly one every
  7 minutes.
- Dominated by **`ConnectionRefusedError` (280)** and **`TimeoutError` (149)**. The cascade per wedge
  is `capture attempt failed` -> `resetting scope` -> `STOP/*CLS failed` -> `Error applying UL/AE/SP`
  -> `Error applying acquisition settings` -> (usually) recovery on attempt 2.
- Net cost: **1 sweep skipped of 3778 (0.026 %)** — the one time attempt 2 also failed
  (`Empty PRE? for CHAN1`, 39 occurrences; 40 `capture attempt 2 failed`).

`ConnectionRefused` (the scope actively refusing a new TCP connection, not merely slow) dominating
points at the **scope's own LXI/SCPI socket server** dropping or capping connections, not just
network latency — worth distinguishing early.

## Why it matters
Masked, not solved. At 500 k points the retry path is doing heavy lifting; a worse night, a higher
point count, or a scope that refuses for longer than the retry window turns "0.026 % loss" into real
gaps. The error volume (468 lines) also buries genuinely new problems in the log.

## Directions to investigate
- **Root-cause the ConnectionRefused:** does the scope's socket server cap concurrent/rapid
  connections? Are we opening a **fresh socket per sweep** instead of holding one? A held,
  health-checked session may remove most of the churn — the same move `keep_connected` made for the
  OE BLE link.
- Scope firmware / LXI settings; network path (switch, cabling); read the scope's own error queue
  (`SYST:ERR?`) at the moment of refusal.
- Whether lowering point count or raising `sweep_retries` is an acceptable stop-gap where zero loss
  is required.

## Reusable asset — a full scope autodetect already exists on moj but is bypassed
Investigated 2026-08-22 (Kim: "AutoDetectScope-branchen kan selv finde scopet hvis IP skifter"). The
capability is **not** something to salvage off the old `AutoDetectScope` branch — it already lives on
moj, unused:

- **`py/scope_utils.py` → `ScopeManager`** resolves the scope in order: (1) cache (`scope_cache.json`,
  last host+port, connection-tested first), (2) **hostname candidates** (`scope.local`, `msox-2024a`,
  `msox.local` — mDNS, IP-independent), (3) VISA enumeration, (4) full subnet scan (192.168.0/1.x +
  10.0.0.x, ports 5025/5555/4000/4980). Fast paths first, scan only as last resort.
- **But `open_scope_with_autodetect()` in `acquire_scope_data.py` bypasses it:** if `config["scope_ip"]`
  is set — which the UI always sets — it opens that fixed IP via PyVISA, and `ScopeManager` is only the
  fallback for a missing IP. So the 13 h run ran on a hardcoded IP and the autodetect was dead code.
  Consequence: on `ConnectionRefused` the retry loop re-hits the **same** fixed IP forever, and an IP
  change kills the run outright.

**Fix direction (cheap — it reuses code we already have):**
1. Wire `ScopeManager` into the **failure path**: on `ConnectionRefused`/timeout past N retries, fall
   through to autodetect (cache → hostname → VISA → scan), refresh `scope_cache.json`, reconnect. This
   composes with the held-session idea above — hold one session; on drop, rediscover + reopen instead
   of hammering a dead socket.
2. Complement: set `scope_ip` to the **mDNS hostname** (`scope.local` / `msox-2024a`) instead of a
   numeric IP → IP-change-immune with no code change. **Needs a rig test** that mDNS resolves on that
   network (Pi).

## Acceptance
- The dominant failure mode is identified (socket-cap vs network vs firmware) with evidence.
- Either the wedge rate is materially reduced, or the run is provably safe against it (a
  connection-hold + health-check, or a documented bounded-loss guarantee).

## Owner / test
- **Dev:** diagnose + mitigate. **Tester (Pi):** reproduce the wedge, capture `SYST:ERR?` at refusal,
  measure the wedge rate before/after any change on a multi-hour run.
