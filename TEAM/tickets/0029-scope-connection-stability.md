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

## Acceptance
- The dominant failure mode is identified (socket-cap vs network vs firmware) with evidence.
- Either the wedge rate is materially reduced, or the run is provably safe against it (a
  connection-hold + health-check, or a documented bounded-loss guarantee).

## Owner / test
- **Dev:** diagnose + mitigate. **Tester (Pi):** reproduce the wedge, capture `SYST:ERR?` at refusal,
  measure the wedge rate before/after any change on a multi-hour run.
