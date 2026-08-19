---
id: 0007
title: Robust tach firmware — timeout, glitch rejection, median filter, diagnostics
area: firmware
role: dev
status: done
assignee: pi-claude
depends_on: 0002, 0003
branch: ticket/0007-robust-tach-firmware
pr:
---

## Goal
Make the RP2040 tach handling robust and self-diagnosing, independent of the load-cell
auto-scale. Fixes real defects and turns the firmware into a tool for the EMI-vs-optics test.

## Why (from the firmware read of `main.cpp`)
The current tach is defenceless:
```c
void tach_isr(){ now=micros(); if(prev) last_period_us=now-prev; last_edge_us=now; tach_pulses_total++; }
float compute_rpm(){ if(!last_period_us) return 0; return 60/((last_period_us/1e6)*PULSES_PER_REV); }
```
- **No filtering** — every rising edge counts; a stray EMI/reflection edge is a "pulse".
- **rpm from only the last two edges** — one stray edge changes the reading.
- **No timeout** — lose the signal and `last_period_us` holds → rpm freezes at the last value.

This is why ticket 0002's artifact looks the way it does: a **steady** spurious edge rate reads
straight through as an additive offset (`measured = true + 60·f_spurious`; +234 rpm at standstill,
+582 running).

## Honest scope
Firmware robustness **cannot remove a steady slow spurious offset** — the spurious pulses here are
~4–10 Hz (100–250 ms apart), indistinguishable from real pulses at low rpm, so no debounce/median
kills them. **The source fix is hardware (ticket 0003: shielding / grounding / optics).** What this
ticket *does* deliver: fixes the frozen-value bug, rejects fast glitches / double-edges, smooths
outliers, and — most usefully — **exposes a glitch/pulse count so the spurious source can be
measured at the rig without a scope.**

## Reference implementation (drop into `firmware/src/main.cpp`)

Constants (near `PULSES_PER_REV`):
```c
const uint32_t TACH_TIMEOUT_US    = 1500000;  // no accepted edge 1.5 s -> rpm 0 (min real 100 rpm = 600 ms, safe)
const uint32_t TACH_MIN_PERIOD_US = 8000;     // 8 ms => >7500 rpm, impossible (max real 3000 rpm = 20 ms). Assumes PPR=1.
const int      TACH_MEDIAN_N      = 5;
```
Globals (replace the three tach volatiles):
```c
volatile uint32_t tach_pulses_total = 0;   // every raw rising edge (incl. rejected)
volatile uint32_t tach_glitch_total = 0;   // edges rejected as too-close (glitch / double-edge)
volatile uint32_t last_edge_us = 0;        // timestamp of last ACCEPTED edge
volatile uint32_t last_period_us = 0;      // last accepted period
volatile uint32_t tach_periods[TACH_MEDIAN_N] = {0};
volatile int      tach_period_idx = 0;
volatile int      tach_period_count = 0;
```
ISR + rpm (replace `tach_isr` + `compute_rpm`):
```c
void IRAM_ATTR tach_isr(){
  uint32_t now=micros(); uint32_t prev=last_edge_us;
  tach_pulses_total++;
  if(prev){
    uint32_t dt=now-prev;                 // unsigned: rollover-safe
    if(dt<TACH_MIN_PERIOD_US){ tach_glitch_total++; return; }  // glitch: ignore, keep last real edge
    last_period_us=dt;
    tach_periods[tach_period_idx]=dt;
    tach_period_idx=(tach_period_idx+1)%TACH_MEDIAN_N;
    if(tach_period_count<TACH_MEDIAN_N) tach_period_count++;
  }
  last_edge_us=now;
}
float compute_rpm(){
  noInterrupts();
  uint32_t le=last_edge_us; int n=tach_period_count; uint32_t p[TACH_MEDIAN_N];
  for(int i=0;i<n;i++) p[i]=tach_periods[i];
  interrupts();
  if(n==0) return 0.0f;
  if((uint32_t)(micros()-le)>TACH_TIMEOUT_US) return 0.0f;     // signal lost / shaft stopped
  for(int i=1;i<n;i++){ uint32_t k=p[i]; int j=i-1; while(j>=0&&p[j]>k){p[j+1]=p[j];j--;} p[j+1]=k; }
  uint32_t med=p[n/2];
  if(med==0) return 0.0f;
  return 60.0f/((med/1e6f)*PULSES_PER_REV);
}
```
New diagnostic command (keep `SPEED?` wire-compatible; add `TACHDIAG?`):
```c
void cmd_tachdiag(){
  noInterrupts(); uint32_t pl=tach_pulses_total,gl=tach_glitch_total,lp=last_period_us; interrupts();
  Serial.print("OK TACHDIAG pulses="); Serial.print(pl);
  Serial.print(" glitches=");          Serial.print(gl);
  Serial.print(" accepted=");          Serial.print(pl-gl);
  Serial.print(" last_period_ms=");    Serial.print(lp/1000.0,3);
  Serial.print(" ts=");                Serial.print(now_unix_ms());
  Serial.print("\r\n");
}
// parser: else if(!strcmp(cmd,"TACHDIAG?")) cmd_tachdiag();
```
Bump `FW_VERSION` → `"1.2.1"`.

## Deployment note (the flashed board is v1.1.0, pre-auto-scale)
This tach change touches **only** the tach code — orthogonal to auto-scale. Two options:
- **(recommended) Isolate:** backport it onto v1.1.0 → flash a tach-only fix, verify the tach in
  isolation without dragging in auto-scale + per-gain re-calibration.
- Or fold into the v1.2.0 source on `moj` and flash auto-scale + robust-tach together (needs re-cal).

## Acceptance
- Compiles for the RP2040 target; `SPEED?` unchanged on the wire (same fields, robust value).
- `TACHDIAG?` returns `pulses`, `glitches`, `accepted`.
- **Timeout works:** shaft stopped with a truly dead signal → `SPEED?` rpm goes to 0 (no freeze).
- **Diagnostic (the point):** shaft stationary → `TACHDIAG?` accepted-count rises at the spurious
  rate (~3.9 Hz ≈ 234 rpm). Energise the drive at 0 Hz → does the rate jump toward ~9.7 Hz? If yes,
  it confirms VFD/motor EMI (ticket 0003) — cabling/shielding, not optics.

## Owner / test
- **Dev:** integrate + compile + flash. **Tester (Pi, rig free now):** flash, confirm SPEED?/TACHDIAG?,
  timeout, and run the stationary-shaft + drive-at-0-Hz discriminating test. Re-cal only if flashed via v1.2.0.

## Implementation (Pi, 2026-08-19) — built, flashed and verified on the rig

Done **both** ways the ticket offered, because they serve different purposes:

| Build env | Source | Version | Purpose |
|---|---|---|---|
| `seeed-xiao-rp2040` | `firmware/src/main.cpp` | **1.2.1** | forward path: auto-scale + robust tach |
| `seeed-xiao-rp2040-tach-v111` | `firmware/src_tach_v111/main.cpp` | **1.1.1** | isolated tach-only fix to flash now |

The isolated build is v1.1.0 — the version actually on the board — plus the tach changes and
nothing else, selected with `build_src_filter` so PlatformIO compiles only that source (two
`setup()`/`loop()` definitions in one build would fail at link).

**Verified by inspecting the built binaries**, not by assumption:

| env | version string | `TACHDIAG` | `AUTOGAIN` |
|---|---|---|---|
| `seeed-xiao-rp2040` | 1.2.1 | present | present |
| `seeed-xiao-rp2040-tach-v111` | 1.1.1 | present | **absent** |

That absence is the point: flashing the isolated build cannot disturb the load cell, so no
re-TARE and no per-gain SETCAL are needed.

Both compile clean. Cost on the v1.2.x build: +32 bytes RAM, +464 bytes flash.

### Notes on the reference implementation
- `IRAM_ATTR` is an ESP32 idiom, but both sources already carry
  `#ifndef IRAM_ATTR / #define IRAM_ATTR`, so it is a harmless no-op here. Checked before use.
- v1.1.0 has a different tach architecture from v1.2.0 — a `TachSnapshot` struct with an
  atomic read — which is cleaner than v1.2.0's direct volatile access. The backport keeps that
  pattern rather than forcing v1.2.0's shape onto it, so the snapshot now also carries
  `glitch_total`, `last_edge_us` and the period ring.
- `TachSnapshot` is declared above the constants and must size its array with a literal, so a
  `static_assert` guards it against drifting from `TACH_MEDIAN_N`.
- The old v1.1.0 filter was `dt > 100` (100 µs — contact bounce only). Replaced by the 8 ms
  floor, which also rejects fast electrical spikes.

### Acceptance status
- [x] Compiles for the RP2040 target (both envs).
- [x] `SPEED?` unchanged on the wire — same fields, same order; only the value is now median-
      filtered and timeout-aware.
- [x] `TACHDIAG?` implemented, returning `pulses`, `glitches`, `accepted`, `last_period_ms`, `ts`.
- [ ] **Timeout verified on hardware** — needs a flash.
- [ ] **The diagnostic itself** (stationary-shaft accepted-rate, then drive at 0 Hz) — needs a flash.

**Not flashing without a go-ahead.** The board is the rig's only tacho and load-cell interface;
the architect asked to be pinged first, and Kim should know the rig is being touched.

## Flashed and verified on the rig (2026-08-19)

Flashed `seeed-xiao-rp2040-tach-v111` (the isolated build).

| check | result |
|---|---|
| `INFO` | **fw=1.1.1** |
| `CAL?` | `slope=0.008047 tare=339992 gain=64` — **unchanged**; the load cell was untouched, so no re-TARE and no per-gain SETCAL |
| `SPEED?` | same fields and order; reads **rpm=0.0** with the shaft stopped, where 1.1.0 had been frozen at 156.44 minutes earlier |
| `LOAD?` | still answers (still railed at `raw=8388607` — auto-scale territory, ticket 0003) |
| `TACHDIAG?` | returns `pulses`, `glitches`, `accepted`, `last_period_ms`, `ts` |

**The freeze bug is dead**, demonstrated directly: 1.1.0 reported 156.44 rpm on a stationary
shaft; 1.1.1 reports 0.0.

Also added a `tachdiag` subcommand to `util_tool.py`, which had none.

### The diagnostic did its job — see ticket 0003

| state | accepted pulses (60 s) | rate |
|---|---|---|
| drive OFF, shaft stationary | **0** | **0.00 Hz** |
| drive ENERGISED at 0 Hz, shaft stationary, 0.0 A | **579** | **9.65 Hz** = 579 rpm-equivalent |

9.65 Hz × 60 = 579 rpm against the **+582 rpm** offset measured across two 13 h runs. Zero
glitches rejected, and edges spaced a regular 103.4 ms apart — these are clean, well-spaced
pulses, not fast spikes, which is why no firmware filter can remove them.

**Correction to ticket 0002/0003:** the "234 rpm phantom at standstill" was a *frozen* value from
the timeout-less firmware, not live spurious pulses. With the timeout there are zero pulses when
the drive is off. There is no always-present background source — there is one source, the drive,
and it accounts for the whole offset.

### Acceptance
- [x] Compiles for the RP2040 target (both envs)
- [x] `SPEED?` unchanged on the wire
- [x] `TACHDIAG?` returns pulses/glitches/accepted
- [x] **Timeout works** — shown by rpm falling to 0.0 on a stationary shaft where 1.1.0 froze.
      The deliberate cover-the-sensor test is still pending, at Kim's request, until he is at the rig.
- [x] **Diagnostic** — stationary 0.00 Hz vs drive-energised 9.65 Hz. VFD EMI confirmed.
