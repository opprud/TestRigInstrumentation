---
id: 0029
title: Scope connection stability — 114 wedge/recovery cycles in the 13 h run; reproduce-under-load
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
retry machinery recovers almost all of it, so it is nearly invisible in the data — but it is frequent,
and the run is one un-recovered retry away from losing a sweep (it lost exactly one).

## Evidence — 13 h run `20260820_125647` (`acquire_scope.log`)
- **468 error lines**, **114 "resetting scope" wedge/recovery cycles** over 13 h — roughly one every
  7 minutes.
- Dominated by **`ConnectionRefusedError` (280)** and **`TimeoutError` (149)**. The failing operations
  are `connect`, `PRE?` and `DATA?` — the **heavy transfer path**, under acquisition load (~3 MB/sweep
  across three channels every 12 s). The cascade per wedge is `capture attempt failed` -> `resetting
  scope` -> `STOP/*CLS failed` -> `Error applying UL/AE/SP` -> `Error applying acquisition settings` ->
  (usually) recovery on attempt 2.
- Net cost: **1 sweep skipped of 3778 (0.026 %)** — the one time attempt 2 also failed
  (`Empty PRE? for CHAN1`, 39 occurrences; 40 `capture attempt 2 failed`).

## Why it matters
Masked, not solved. At 500 k points the retry path is doing heavy lifting; a worse night, a higher
point count, or a scope that refuses for longer than the retry window turns "0.026 % loss" into real
gaps. The error volume (468 lines) also buries genuinely new problems in the log.

## Hypotheses tested and REFUTED — idle scope (2026-08-22, scope-only, no motor)
Three mechanisms were measured directly against the instrument while idle; all three fail. Recorded so
they are not re-run:
- **Connection churn** — 25× (open -> `*IDN?` -> close): 1st 9.02 s (cold), then 0.01–0.48 s flat, 0
  failures, no creeping latency, no refusals. Sequential churn of light connections does not produce
  refusals.
- **Single-session limit** — a second socket opened while the first was live was accepted instantly,
  answered `*IDN?`, and the first kept working. No one-connection cap; a recovery socket racing a
  not-yet-closed one is not the mechanism.
- **Held vs fresh cost** — a held connection answers in 0.009 s median vs 0.48 s per fresh connect
  (**54× cheaper**). Real and worth having, but a *cost*, not a failure mode; it does not explain 114
  wedges.

**Scope of the refutation, stated precisely** (so the negative is not over-read the way the positive
nearly was): this kills *churn / limit / concurrency as standalone causes on an **idle** scope with
light payloads*. It does **not** test churn + 3 MB transfers + live digitising together, which is the
run's actual condition.

## What IS established
1. Refusals are **not** caused by churn rate, a connection limit, or concurrency (idle scope).
2. **The SCPI socket (5025) is healthy at rate** — 25 fresh connects run 0.48 s flat with no refusals; a
   held session answers in 0.009 s (54× cheaper) and stayed clean 25/25 (max 0.012 s). So the scope *can*
   hold a session, and the HTTP daemon's cold-path slowness (next point) does **not** carry to the
   acquisition port — don't chase the 11 s HTTP number as an acquisition-path cause.
3. **First contact after idle is very slow** — 9.02 s first connect (5025), 10.95 s first HTTP GET of a
   3.5 KB page on a 0.5 ms-ping direct link. The LAN stack has an expensive cold path, then warms.
4. The scope's web UI is reachable (ports 80/443/5024/5025/111 open); network-side config (below) can be
   done from a browser, no front panel needed.

## Live hypothesis (untested — for the under-load run to settle)
Failures are on the **heavy transfer path under load**, and an idle scope cannot reproduce them. One
thread survived the idle tests: after a connection **drops under load**, the recovery *reopen* may hit
a transiently cold/busy stack (cf. the 9 s cold path) and time out — which would present exactly as the
observed `connect` / `TimeoutError`. A hypothesis to **test**, not a claim; it is the bridge between the
cold-path number and the failing path.

## Next measurement (the honest one)
A short **profiled run** with the existing settings, instrumented to log at every failure: the elapsed
time of the failing op, which op (`connect` / `PRE?` / `DATA?`), `SYST:ERR?` read from the scope at that
moment, whether it followed a reconnect, and the sweep's transfer size; plus per-sweep transfer time
throughout, so creeping latency before a failure is visible. This turns 0029 from "wedges intermittently,
retry absorbs it" into a measured mechanism. Needs the rig + a short run (Kim / Pi).

## Improvements worth doing regardless of the mechanism
- **Reuse the connection in the *recovery* path.** The per-sweep path already holds one connection; the
  recovery path reopens. Reuse there is the 54× per-query win and *may* incidentally reduce wedges (fewer
  cold reopens) — framed as optimisation + hypothesis, **not** the proven fix.
- **Network-side, from the scope's web UI** (kills the IP-change worry, separate from the wedges):
  a **static IP** on a /24 (stable address; also makes `ScopeManager`'s existing 192.168.1.x scan range
  valid + small), *or* **enable mDNS** on the scope (it currently announces nothing — `avahi-browse -at`
  shows no `_scpi-raw` / `_lxi` / `_vxi-11` / `_http`), so `scope.local` resolves.

## Footnote — scope autodetect already exists but is bypassed (not the wedge fix)
`py/scope_utils.py` -> `ScopeManager` does cache -> hostname/mDNS -> VISA -> subnet-scan, but
`open_scope_with_autodetect()` uses the fixed `config.scope_ip` whenever it is set (always, from the UI),
so `ScopeManager` is dead code. On *this* link-local rig it buys ~nothing against an IP change anyway: its
scan range is hardcoded to 192.168/10.x (not the rig's 169.254.x) and a /16 is 65k addresses; only the
network-side fixes above make it viable. Recorded so it is not re-proposed as the wedge fix.

## Acceptance
- The dominant failure mode is identified **under load** (with `SYST:ERR?` at the moment of refusal) with
  evidence — not asserted from idle tests.
- Either the wedge rate is materially reduced, or the run is provably safe against it (a documented
  bounded-loss guarantee).

## Owner / test
- **Dev:** design + instrument the under-load run; implement recovery-path connection reuse. **Tester
  (Pi):** run it, capture `SYST:ERR?` + elapsed at each failure, measure the wedge rate before/after any
  change.
