# Maintenance log

Append-only record of **physical changes to the rig** — what it *is*, so the data can be read
against it. A rebuild is a **hard boundary**: absolute signal levels do not carry across it (new
surfaces, new clearances, new preload), so the first run after any entry here is a deliberate
**re-baseline**, not a warm-up (see `CLAUDE.md`). Where a build fact should also travel *inside* the
data, stamp it into `/metadata/ground_truth` on the run's HDF5 (Pi's stamper).

---

## 2026-09-02 → boundary: bearing bushing + lock rings replaced (root cause: self-loosening nut → bearing slip)

**Status (2026-09-23): rig CLOSED — rebuild accepted.** The stroboscope re-test at running speed was
run by Kim on 2026-09-23 and **passed: nothing crept.** That was the acceptance gate, so the rebuild is
complete and runs have resumed. The bring-up that preceded it is the 2026-09-23 entry below.

**Discovery.** With a **stroboscope** set to the shaft frequency (which freezes the rotation), the
bearing was seen **slipping on the shaft** and the retaining **nut slowly loosening itself under
drive** — a reference mark that should have been frozen instead crept.

**Root cause.** The tightening specification was **never followed** → too little preload → classic
vibration **self-loosening** of a nut on a rotating shaft (Junker effect) → loss of axial clamp →
the bearing slips on the shaft → wear of the **bushing** (the running surface). Because the spec was
never followed, the retaining ring / clamp was **probably loose across all historical runs**, not
just the recent ones — so ring/clamp state is unknown for every run before this rebuild, the three
13 h runs included.

**Planned / in progress (rig down since 2026-09-02).**
- New **bushing / bearing seat** — `<part no. — TBD Kim>`. The old one was worn by the slip.
- New **lock rings** — `<part no. — TBD Kim>`.
- Retaining bolt: **finger-tight, then +90° with the tool wrench.** Positive lock = **tab washer** —
  bend its wings out against the bolt head so it cannot back off (this is the anti-self-loosening
  feature that was missing; friction alone does not hold a bolt on a rotating shaft).
- As-built (record while apart): radial clearance `<TBD>`, preload `<TBD>`, ring seated: `yes`.
- **Reassembly distances — RESTORE these on rebuild** (measured 2026-09-18, rig apart):
  - Motor magnet ↔ axle magnet gap: **3 mm**
  - Axle-disk end ↔ bearing-holder end gap: **31.5 mm**

**Data impact.** 2026-09 is a hard boundary — **absolute levels void, re-baseline.**
Rotation-correlated / impulsive readings in historical data carry an uncharacterised mechanical
artefact (the slip). The **UL-vs-temperature finding survives** (it reproduced across two 13 h runs
with the 0 rpm floor flat in both, and ring state was shown not to move UL amplitude beyond the
~26 % run-to-run wander) but is **re-confirmed on the first post-rebuild run**.

**Prevention (now procedure, not a note).** Torque-to-spec + a positive lock, recorded here; and the
**strobe check** is in `docs/Prerun_Checklist.md` §2 — strobe the shaft at speed after any reassembly
and spot-check it on long runs. A creeping mark = slip / self-loosening, caught before it wears
anything. This is the missing procedure that caused the whole ring saga; the fix is the written
procedure, not tightening harder this once.

---

## 2026-09-23 → post-rebuild bring-up: clamp load re-set, load cell re-tared, sensors checked

**Status: rig still OPEN.** The strobe acceptance gate above has **not** been recorded as passed, and
the tachometer cannot be used (below). Nothing here closes the rebuild — this is bring-up, not
acceptance.

**Motor spin check — passed.** Driven straight over Modbus from the command line (no backend, no scope,
no heater), 30 s each at 10.00 / 20.00 / 30.00 Hz. The drive followed every step exactly, reported no
fault, and Kim confirmed by eye that the shaft turned properly. Stopped and confirmed stopped at the
register afterwards.

**Load cell re-tared in place, unloaded**, before tightening: `tare` **720481** (gain 128) / **361668**
(gain 64); band ratio 1.992; unloaded reads within ±0.8 g. The 2026-08-25 zero had drifted 150 g across
the teardown, as expected — the zero travels with the mechanics, only the slope travels with the unit.

**Clamp load re-set to an estimated ~142 kg over 8 turns**, anchored on the last measured value
**71.14 kg at 4 turns**. Per-turn increments while still measurable: +16.8 / +18.7 / +20.1 / +15.5 kg
(mean 17.8) — **markedly more repeatable than the pre-rebuild +19.9 / +13.9 / +31.5**. Final figure
carries ~±20 kg. Full 2 Hz trace: `py/data/loadcell_tightening_20260923.log`.

> **Record the anchor, not the estimate.** 71.14 kg / 4 turns is the only measured point on the way up
> and the only thing a later attempt to reproduce this load can aim at.

**Reassembly distances (3 mm magnet gap, 31.5 mm axle-disk ↔ bearing-holder) — not verified by this
session.** They are recorded above as "restore on rebuild"; whether they were restored is Kim's to
confirm, and it is not visible from the instrumentation.

**OE BLE sensor — working.** Re-powered and re-tested: advertises as `OE00031204100074` at
`03:24:71:01:04:54`, **RSSI −49 dBm** (every other BLE device in the room sat at −82 to −96). Three
consecutive connect→sample→disconnect cycles, **three successes**, 16.4 / 26.0 / 23.5 s. Both mics
returned live, varying data at rest: machine mic 74752 samples rms 2.72, ambient 74153 samples rms 2.01
— the machine mic 35 % hotter than ambient, as it should be when coupled to the bearing. None of the
August sleep-window or connect failures reappeared.

**Tachometer — was dead, now REFITTED AND VERIFIED (same day).** It first read 0.0 rpm at all three
speeds with `TACHDIAG?` showing 1 pulse / 0 glitches across 90 s of confirmed rotation: the reflective
mark was missing from the shaft after the rebuild. Kim refitted the tape and it was re-measured against
commanded drive frequency, every setpoint verified before reading:

| drive Hz | expected | measured | deviation |
|---|---|---|---|
| 5 | 287.5 | 280.6 | −2.4 % |
| 10 | 586.6 | 560.9 | −4.4 % |
| 15 | 885.8 | 876.3 | −1.1 % |
| 20 | 1184.9 | **1176.1** | **−0.7 %** |

One glitch in 724 pulses. `rpm_meas` is usable again and `Prerun_Checklist.md` §3 can be performed.
**rpm/Hz runs consistently below the 2026-08-19 calibration** (56.1 vs 57.6 at 5 Hz; 58.8 vs 59.5 at
20 Hz) — more slip, as the ~142 kg clamp load should produce. Re-measure the factor if absolute speed
matters.

**Drive fault found while doing it — writes degrade on a held connection.** Five writes of 30 Hz and
five of 40 Hz all failed (`cmd=0.00` readback), then **six `stop()` calls failed on a shaft turning at
1176 rpm**; a fresh connection stopped it first try. Reconnect rather than retry. Details in
`CLAUDE.md`. Motor confirmed stopped by tach (rpm 0 + frozen pulse count) and by Kim reading 0 Hz on the
drive panel.

**Firmware defect found during the tightening:** auto-gain never steps 128 → 64 under rising load and
saturates at ~35 kg — **ticket 0045**. Worked around by pinning gain 64 by hand (RAM-only).

### Outstanding
- [x] ~~Strobe pass at running speed~~ — **run by Kim 2026-09-23, passed, nothing crept.** Gate closed,
      rebuild accepted, runs resumed.
- [x] ~~Reflective mark refitted and the tach verified~~ — done 2026-09-23, table above.
- [ ] Bolt torque + part numbers still `TBD` in the entry above.

---

## 2026-09-23/24 → first 13 h run after the rebuild — the post-rebuild BASELINE

`20260923_125909`, Keratech 22 profile, 12:59:09 → 02:12:24 (13.2 h). **This is the re-baseline run** the
2026-09-02 entry called for: every absolute level recorded after the rebuild is read against this one.

**Preceded by a 15 min smoke test** (`20260923_124133`, `NoiseFloor_SmokeTest_15min`) which passed on
every point: 74 sweeps, 0 skipped, 500 k points/channel, all three scope channels valid and
speed-responsive, SP mean +4.996 V (probe ground attached), OE 3/3 cycles.

| | |
|---|---|
| sweeps | **3964 — 0 skipped, 0 gaps in numbering** |
| scope resets | **0** (August's run: 114 over 3778 sweeps) |
| points | 500 000 per channel × 3 (1 M requested, scope clamps to 500 k with 3 channels) |
| speed tracking | 6769+ stationary ticks, median **−0.30 %**, none beyond −3.4 % |
| temperature | all 13 steps 40 → 100 C; PV within ±2 C of SV throughout |
| OE | **152 captures**, 7 lost windows, 4 reconnects — **95.6 % yield** (documented norm 94 %) |
| file | 4.26 GB, md5 `0c41ef4b3a2e65c41cf8135d25281817` |
| archive | `csfbst001` / **`eceherning`** / `20260923_125909/` — h5 **plus** the telemetry JSONL, the event log and the heater-guard log, all four MD5-verified on upload |
| heater | switched off and **VERIFIED OFF by the guard at 02:16:00**; PV 98 → 54 C over 17 min |

> **These blobs carry a content-MD5, unlike the three 13 h runs of August** — they can be proven
> byte-exact later without re-downloading. The sidecars are archived too, so the per-tick record no
> longer exists only on the SD card.

**Rig state during the run:** clamp load ~142 kg estimated (anchor 71.14 kg at 4 turns, 2026-09-23), so
`LOAD?` returns `ERR 21` throughout and `mass_g` is null in every telemetry tick — expected, not a fault.
Lubricant metadata corrected before the run to Keratech 22 applied 2026-09-23 on the rebuilt bearing.

### Finding: UL vs oil temperature — direction reproduces, magnitude halved, and one confound

UL RMS at fixed speed, 40 C → 100 C: **−14.3 %** (1500 rpm), **−36.8 %** (2000), **−30.4 %** (2500),
**−21.4 %** (3000). The **0 rpm floor stayed flat (+6.6 %)**, which is the control that matters: had the
probe or its gain drifted over 13 hours, the floor would have moved with the rest.

Pre-rebuild the same finding measured −42 to −50 %. So it **reproduces in direction on a rebuilt rig with
a correctly seated retaining ring**, at roughly half the strength.

> **But the profile cannot separate temperature from time-since-start, and the shape says that matters.**
> Almost the whole fall happens between the 40 C and 50 C steps and the curve is flat from 50 C to 100 C
> — at 2000 rpm, 0.804 → 0.732 → 0.539, then 0.51-0.58 for the remaining ten steps. That is the shape of a
> **first-hour transient**, not of a continuous temperature dependence; and since the profile ramps
> monotonically from a cold start, "40 C" is also "the first hour". Bedding-in of a freshly rebuilt
> bearing would look exactly like this. The flat 0 rpm floor does not rule it out, because a stationary
> bearing has nothing to bed in.
>
> **The experiment that separates them:** take the temperature back *down* again, or hold one speed and
> cycle temperature up and down. If UL climbs back as the oil cools it is temperature; if it stays low it
> was bedding-in. Cheap, and it is the next run worth doing.
