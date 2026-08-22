---
id: 0029
title: Scope connection stability — wedge every ~50 sweeps, reproduces bench scope-only (rig/EMI out)
area: acquisition
role: dev
status: backlog
assignee: unassigned
depends_on:
branch:
pr:
---

## Problem
The scope's TCP connection wedges — `connect` / `PRE?` / `DATA?` refused or timing out — at a fixed
period during acquisition. The retry machinery recovers almost all of it (the 13 h run lost 1 sweep of
3778, 0.026 %), so it is nearly invisible in the data, but it is frequent and one bad retry from a gap.

## Established (measured, 2026-08-22)
1. **Metronomic period — every 50±1 sweeps.** In the 13 h run (`acquire_scope.log`, 114 resets at 74
   distinct sweeps) the failing sweeps are 46, 96, 147, 198, 248… — delta histogram {49:1, 50:22, 51:50},
   inter-arrival CV 0.72 (regular, not bursty). No wedge-free stretch longer than 10.8 min; every 50-min
   window holds 4–10 wedges (P(0)=0 %). Our recovery (`:STOP`+`*CLS`+re-apply) restores ~50 clean sweeps
   — the reset *clears* whatever accumulates.
2. **Reproduces on the bench, scope-only — rig and EMI are out.** A 250-sweep run matching only the 13 h
   run's *scope* load (3 ch, points MAX, 1 M, 12 s, retries 2), no motor / no heat / VFD idle, wedged at
   **sweep 44** — same failing step (`connect` timeout), same signature, two sweeps from the run's 46. The
   mechanism lives entirely in the scope's transfer path. **0029 is now a ~9-minute bench loop:** no motor,
   heat, bearing wear, lubrication or 13 h needed for any future measurement.
3. **Cold path slow, warm SCPI socket healthy** — first connect after idle 9.0 s, first HTTP GET 11 s;
   but 25 warm fresh connects run 0.48 s flat with no refusals, a held session answers 0.009 s and stays
   clean 25/25. The HTTP daemon's slowness does not carry to 5025, and the scope *can* hold a session.
4. Web UI reachable (ports 80/443/5024/5025/111 open); the network config below is browser-doable.

## What the idle tests did and did NOT show
The idle-scope probes ran at **≤25 light `*IDN?` connections** — below the ~44–50 threshold and with no
heavy transfer. They show *light-payload churn ≤25 is clean, no single-socket cap at 2 concurrent, 5025
healthy at rate* — but they **did not reach the mechanism** and do not refute it. "Single-session limit
refuted" must read **"≤25 fine; ~50 untested."** The accumulation hypothesis is alive; the idle tests
simply stopped short of where it breaks.

## Open question — the mechanism (discriminator in flight)
Something accumulates ~1 unit per heavy acquisition, saturates ~50, and is cleared by our reset. Two
transfer-path candidates, with a clean fork between them:
- **Socket churn** — `socket_capture_sweep` opens a fresh socket per sweep; against the slow-to-reap scope
  stack, ~50 TIME_WAIT/half-open sockets could exhaust the SCPI listener → connect refused/timeout. Fits
  everything: slow stack + ConnectionRefused-dominance + the period + reset-clears-it + the clean held arm.
- **Per-`:DIGITIZE` accumulation** — acquisition memory / status / error queue filling per acquisition,
  independent of the connection.

**Discriminator (test 2, bench, minutes):** re-run holding ONE connection across all sweeps.
- clean → socket churn confirmed; **reuse-one-connection is the fix** (promoted from efficiency on
  measured evidence).
- still wedges at ~50 → not sockets; **2b:** held + proactive `:STOP`/`*CLS` every ~40 sweeps → clean
  means status/memory accumulation, fix is a proactive periodic clear (no connection change).

**Test 1 (bench, minutes):** at a wedge, bare-TCP-probe port 80/5024 vs 5025 (whole-stack vs listener),
`ss -tan dst <scope>` for TIME_WAIT depth, and `SYST:ERR?` if a channel can be got before recovery's
`*CLS`.

## Improvements (one may be the fix, pending the discriminator)
- **Reuse the connection across sweeps / in recovery.** The per-sweep path opens per sweep; recovery
  reopens. If test 2 comes clean this *is* the fix; either way it is a 54× per-query win.
- **Network-side, from the web UI** (kills the separate IP-change worry): a static IP on a /24 (stable
  address; also makes `ScopeManager`'s 192.168.1.x scan valid), or enable mDNS (the scope announces
  nothing today — `avahi-browse` shows no `_scpi-raw`/`_lxi`/`_vxi-11`/`_http`).

## Footnote — scope autodetect exists but is bypassed (not the wedge fix)
`py/scope_utils.py` → `ScopeManager` (cache → hostname/mDNS → VISA → scan) is dead code because
`open_scope_with_autodetect()` uses the fixed `config.scope_ip` whenever set (always). On this link-local
rig its scan range is wrong (192.168/10.x, not the rig's 169.254.x) and /16 is 65k anyway. Recorded so it
is not re-proposed as the wedge fix.

## Acceptance
- Mechanism named by the discriminator (socket churn vs `:DIGITIZE` accumulation) on bench evidence.
- Fix lands (connection reuse or proactive clear) and a 250-sweep bench run wedges 0 times where it
  wedged ~5.

## Owner / test
- **Dev:** the reuse/clear patch once the discriminator names the mechanism. **Tester (Pi):** run the
  discriminator + test 1 (bench, scope-only), post the full wedge series.
