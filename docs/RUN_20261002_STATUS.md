# Run status — `20261002_122423` (first clean 13 h run after the rebuild)

**Run:** `20261002_122423`  ·  **12:24 → 01:37** (2026-10-02 → 03)  ·  stop reason `duration_reached`
**Profile:** `Keratech22.json`, unchanged (last edited 2026-08-30)
**Oil:** fresh Keratech 22  ·  **Clamp load:** ~150 kg  ·  **Config:** coupled, drive live, heat 40→100 °C
**Data:** `eceherning/20261002_122423/` — h5 **4.39 GB** + telemetry JSONL + `acquire_scope.log` +
`heater_guard.log`, all four **MD5-verified**.

> **Headline: this is the best run the rig has done.** 3964 sweeps, **0 skipped, 0 scope resets**, and it
> settles the scope-hang question (ticket 0029). The rebuild worked.

## 1. Health — this run vs the last comparable 13 h (2026-08-20)
| metric | this run | 2026-08-20 |
|---|---|---|
| sweeps | **3964** | 3778 |
| skipped | **0** | 1 |
| scope reset / recovery | **0** | **114** |
| error lines in the log | **2** | 468 |
| gaps in sweep numbering | **0** | — |
| OE recordings | 157 (2 err, 2 reconnects) | 249 |
| tacho read errors | **0 of 8601 ticks** | — |

The two error lines are the **cold-start LXI rejections** at startup — the deterministic, characterized
scope behaviour, not a fault. **No hanging of any kind.**

## 2. What this run settles
- **Ticket 0029 — the scope hang belonged to the rig *before* the rebuild.** Two consecutive 13 h runs now
  show **zero resets** (2026-09-23: 3964/0, and this: 3964/0), against August's **114 resets per 3778
  sweeps** — one every seven minutes. One clean run was not enough to delete the entry; two identical ones
  are. `sweep_retries` and point count can be sized freely again.
- **rpm/Hz is NOT temperature-dependent (next-step point 6 closed).** At fixed 1800 rpm across all seven
  temperature decades (8601 ticks): 40 °C 59.39, 50 °C 59.23, 60 °C 59.33, 70 °C 59.25, 80 °C 59.39,
  90 °C 59.27, 100 °C 59.21 — **spread 0.18 = 0.30 % over sixty degrees.** The 57–60 variation in the notes
  follows **speed** (slip falls with rpm), not oil temperature; no temperature factor is worth introducing.
  Speed deviation vs `59.83 × Hz − 11.7` had **median 0.29 %** over the run (the tail outliers are
  transition samples during step changes).
- **The rig has no temperature ceiling under 100 °C.** All fourteen SV steps were hit (40→100 °C in 5 °C
  steps + the 25 °C tail) and **100 °C was reached and held** (PV 0 to +4 °C over SV at the cold end, −1 at
  SV 95 during the ramp, then caught up).

## 3. A change from the older runs — read before comparing
**The 100 rpm step now turns the shaft (86 rpm).** CLAUDE.md recorded that step as **0 rpm** (the motor had
too little torque at 1.68 Hz), so its 52 occurrences across the old runs are data on a *stationary* bearing.
With fresh Keratech 22 the static friction is low enough to break away — the same lubrication-state
breakaway seen earlier this day. **The three older 13 h runs therefore cannot be compared with this one at
the lowest speed steps**: they were stationary there, this run rotates. (CLAUDE.md keeps the old post as
"still true of the older runs.")

## 4. Heat — off and confirmed
Shut off and confirmed three ways: the heater guard reached `VERIFIED` / `heater guard done` at 01:41:56;
a manual `--off` confirmed; and PV fell **100 → 93 → 87 → 77 → 65 → 25 °C** to ambient overnight (SV also
25 after the tail). **Caveat (ticket 0006):** the guard's verification was **slow, not blind** — the heat
was already off before the guard's first command, but three attempts returned `state UNKNOWN` over 3.5 min
before the fallback confirmed. The failure is the **verify timeout budget (5 s too short)**, not the
transport; raising it would have made all three attempts `VERIFIED`. It was three attempts from the
2026-08-26 outcome (went off without confirmation while regulating at 100 °C), so the timeout bump is worth
doing now.

## 5. Data quality
- **Nothing clips.** SP reports Vpp 10.21 V in an 8 V window and AE 5.58 V in a 5 V window, but the fraction
  of samples on the rails is **UL 0.0021 %, AE 0.0006 %, SP 0.0028 %** (52 / 16 / 71 of 2.5 M) — isolated
  spikes. The scope digitises **outside** the displayed window (SP reaches −0.606 to 9.606 V in a nominal
  0.5–8.5 V window): **the window is the display, not the ADC's limit.** `Vpp > window` looks like clipping
  at a glance and is not.
- **Resolution is good at signal:** at 2894 rpm AE uses 222 levels, UL 119, SP 254. (The sensor-noise
  *floor* is still quantization-limited at 1.5–2× — see the 0046 report — but a driven run is not.)
- **Load is null the whole run** — the cell sits on its 24-bit rail at the ~150 kg clamp load, as expected;
  the file carries no per-sweep load datum, so **read the clamp load from these notes, not the h5.**

## 6. Platform (ticket 0033)
The Pi came through the thirteen hours **without a single undervoltage event**: `rig-health` took **784
samples, all `throttled=0x0`**; free memory stayed flat at 13539–13788 MB of 16218 (no leak over 13 h); CPU
49.4–56.5 °C. First full day with the persistent journal and sampler in place. It does **not** prove the
freezes are gone (there was no freeze to catch), but it rules out undervoltage and memory pressure for this
night and is a clean baseline to hold the next event against.

## 7. How to read the sensor background on this run
Because this run heated the oil — which none of the 0046 noise blocks did — the heat's duty cycle moves the
sensors, and UL/AE and SP in **opposite** directions (UL/AE up acoustically at full power; SP up via the
relay switching near setpoint). This is characterized in **`docs/0046_REPORT.md` §6** and does not undermine
the UL-vs-temperature finding (heat *masks* it rather than creating it). The first ~1 h is not steady state
(oil-film transient, Prerun checklist §8).

---
*Status written 2026-10-03 from the run's own telemetry and logs (Pi) and the 0046 reference. Numbers are
authoritative in the run's sidecars at `eceherning/20261002_122423/`.*
