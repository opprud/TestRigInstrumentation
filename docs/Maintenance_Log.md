# Maintenance log

Append-only record of **physical changes to the rig** — what it *is*, so the data can be read
against it. A rebuild is a **hard boundary**: absolute signal levels do not carry across it (new
surfaces, new clearances, new preload), so the first run after any entry here is a deliberate
**re-baseline**, not a warm-up (see `CLAUDE.md`). Where a build fact should also travel *inside* the
data, stamp it into `/metadata/ground_truth` on the run's HDF5 (Pi's stamper).

---

## 2026-09-02 → boundary: bearing bushing + lock rings replaced (root cause: self-loosening nut → bearing slip)

**Status (2026-09-05): rig OPEN, work in progress.** It stays down until the new bushing + lock nut
are fitted and a **stroboscope re-test at running speed shows no slip and no nut creep**. That strobe
pass is the acceptance gate to close the rebuild and resume runs — no runs before it.

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

### Outstanding before runs resume
- [ ] **Strobe pass at running speed** — the acceptance gate from the 2026-09-02 entry.
- [x] ~~Reflective mark refitted and the tach verified~~ — done 2026-09-23, table above.
- [ ] Bolt torque + part numbers still `TBD` in the entry above.
