---
id: 0049
title: Sensor channel labelling corrected — UL = UL750 ultrasound, AE = Kistler acoustic emission; OE/BearingBrain MIC is the async 4th sensor
area: documentation / data-quality
role: dev
status: in-progress
---

## The authoritative sensor map (Kim, 2026-10-21)

| Scope CH | Alias | Sensor |
|---|---|---|
| CHAN1 | `UL` | **UE Systems UL750** ultrasound sensor (heterodyne) |
| CHAN2 | `AE` | **Kistler acoustic-emission** probe |
| CHAN3 | `SP` | Slip ring (slæbering) |
| — (async) | `OE` | **BearingBrain "Machine MIC"** — ultrasound mic, FS 100 kHz, BLE, captured into `/oe_samples`, **not synchronously sampled** |

The three scope aliases **read straight**: `UL` = ultrasound, `AE` = acoustic emission, `SP` = slip ring.

## What was wrong

The repo documented the **inverted** mapping: `UL` (CHAN1) as "Kistler acoustic-emission probe" and `AE`
(CHAN2) as a "piezo accelerometer". The root `CLAUDE.md` even flagged it as counter-intuitive ("the alias
`UL` is the acoustic-emission probe and the alias `AE` is the accelerometer") — that framing was simply
wrong, and it propagated into config, the report generator, docs and several tickets.

**Likely cause:** CHAN1 was once the Kistler/AE input (see the stale snapshot in
`docs/hardware_discovery_and_configuration.md`, which has `AE` on CHAN1 and `UL` on CHAN3). When the channel
assignment was reorganised to `UL`=CHAN1 / `AE`=CHAN2, the **descriptive notes did not move with it**.

**Important:** this is a *labelling* error, not a wiring/data error. The data on CHAN1/2/3 is UL750 /
Kistler / slip ring as above; only the human-readable descriptions were wrong.

## Corrected 2026-10-21

- `CLAUDE.md` — canonical channel table (+ added the OE/Machine-MIC async 4th sensor).
- `py/tools/run_report.py` — `SENSOR` dict (fixes all future `NOTE_*.txt` + `spectra_*.html` legends).
- `py/config.json` — CHAN1/CHAN2 `notes` (fixes future HDF channel metadata).
- `py/config_test.json`, `py/config_with_telemetry.json` — legacy `Accel` note.
- `docs/0046_REPORT.md`, `docs/hardware_discovery_and_configuration.md` (stale snapshot banner),
  `docs/Prerun_Checklist.md`, `react/README.md`.
- Tickets `0039`, `0040`, `0048` — the "UL = Kistler" / "AE = accelerometer" phrasings, incl. the demod
  question, which is about the **UL750** (not a Kistler).

## Archive caveat

Every h5, `NOTE_*.txt` and `spectra_*.html` produced **before 2026-10-21** carries the wrong channel
descriptions (UL labelled "Kistler acoustic emission", AE labelled "accelerometer"). The **data is correct**
— only the embedded labels are wrong. Reports regenerated with the fixed `run_report.py` are correct.
`TEAM/BUS.md` history is append-only and left as-is; read its earlier "UL = Kistler" / "AE = accelerometer"
phrasings against this table.

## Interpretation note (flag, not a conclusion)

`UL` being the **UE Systems UL750** — a heterodyne ultrasound detector — is directly relevant to the open
0040/0048 question of whether UL's signal is raw or internally demodulated: a UL750 heterodynes **by
design**. Pi/Kim to confirm against the UL750 datasheet and fold into 0040.

## Open

- **Pi:** verify `acquire_scope_data.py` writes the corrected channel `notes`/attrs into the HDF (so new
  runs carry the right metadata), and regenerate any live-facing report that quoted the old labels.
- The already-run `N0049c` config description still reasons about "the accelerometer" — left as run history;
  covered by the archive caveat above.

## Owner / test
Windows (docs/config), Pi (HDF writer verification). No rig action required.
