# Sensor-channel noise characterization — report (ticket 0046)

**Rig:** ForeverBearing bearing-test rig, Aarhus University
**Period:** 2026-09-30 → 2026-10-02
**Status:** characterization complete; two confirmatory measurements pending (see §7)
**Authors:** Pi (instrumentation / measurement), Windows (architecture / synthesis)

> **Where the data lives.** Every block is archived to **Azure Blob, container `eceherning`**, one folder
> per run at `<run_id>/scope_<run_id>.h5` plus its sidecars (telemetry JSONL, logs, `GROUND_TRUTH.txt` /
> run notes, `content_md5`). The machine-readable floor is `docs/0046_noise_floor.csv` / `.json`
> (63 channel rows); the interactive views are `py/tools/0046_noise_reference.html` (band map, null
> results, caveats) and `py/tools/0046_spectra.html` (log-log spectra, seven configurations), also mirrored
> at `eceherning/0046_REPORT/` with verified MD5. **Prefer those numbers over any scalar quoted in prose.**
> The block → run-id map is in the appendix (§10), so every claim below traces to a specific blob.

## Companion documents (read alongside this report)
- **FFT / spectra figures — `py/tools/0046_spectra.html`.** Log-log averaged periodograms (40-sweep
  averages, DC removed), seven configurations × three channels, 100 Hz–1.25 MHz, crosshair read-out and
  the known lines marked. This is the visual FFT analysis the report's conclusions rest on — a scalar
  cannot show a line nobody looked for (see §8). Also published as an artifact:
  `https://claude.ai/code/artifact/18f492b3-dd25-4d43-8dc9-e1eae73819b7`.
- **Per-run sensor FFT analysis — `docs/RUN_20261002_ANALYSIS.md`.** The Welch-periodogram band breakdown
  of the first clean 13 h run (dynamic range per channel, the band-dependent UL-vs-temperature finding,
  the run-in transient). Companion to the run's status doc `docs/RUN_20261002_STATUS.md`.
- **Uniform band reference — `py/tools/0046_noise_reference.html` + `docs/0046_noise_floor.csv` / `.json`.**
  All 23 blocks, one method (Welch, 38 Hz bins), 3 channels × 9 bands — the authoritative numbers.

---

## 1. Purpose
Find *where* the electrical noise in the three sensor channels (UL = ultrasonic/Kistler, AE =
accelerometer, SP = slip-ring) comes from, and *how much* each source contributes — switch-mode vs linear
24 V supply, the heater/temperature control box, the VFD drive and its sinus (output) filter, the
filter–VFD ground, and the heater relay — so that a long bearing run can be read against a known
background.

## 2. Method — a ladder from silence, one variable at a time
Start from a quiet floor and **add one source at a time**; attribute each by the delta it produces. Every
block uses the same scope channels and acquisition settings so blocks compare without rescaling, and the
configuration (PSU, sinus, motor, drive, box, relay) is recorded in the run notes.

Two disciplines earned their keep and are now standing practice:

- **Made-and-unmade reversal.** A source is only believed when toggling it *back* restores the baseline
  within scatter (e.g. the heater box: ×0.51 off, ×2.27 on). This caught three wrong conclusions.
- **Uniform re-measurement.** All 23 blocks were finally re-reduced by **one** method — 12 sweeps, Welch
  periodogram, 38 Hz bins, 3 channels, 9 bands — because scalar band figures scattered across messages had
  produced contaminated comparisons (§8). That uniform reference is the source of truth.

## 3. Headline results
**Four sources, four bands, no overlap. There is no single noise source to chase; a fix for one does not
touch the others.**

| source | signature | channel(s) |
|---|---|---|
| instrument chain (scope + probe) | 1060.7 kHz | all three |
| heater / temperature control box | 126–135 kHz | AE |
| heater relay | 50–100 kHz | SP strongly, AE weakly |
| drive output stage | broadband | SP (a step with the output active, flat with rpm) |

Two findings outrank the individual numbers:

1. **UL — the main bearing sensor — is electrically clean.** Across all 23 blocks UL is
   **0.0285–0.0304 V rms (±3 %)** regardless of box, drive, sinus filter or relay. At 600 rpm UL reaches
   0.284 V, **9.8× its own floor**; AE and SP sit only 1.8× and 2.7× over theirs, so for them the
   background is a real part of the signal while for UL it is negligible.
2. **The floor is near the instrument's quantization limit — but the *signal* is not.** All three channels
   sit only **1.5–2.0× over the scope's quantization floor** (effectively 8-bit, step = range/199), so much
   of the "broadband" noise in AE and SP at the quiet floor *is* the digitisation — electrical cleanup has
   a hard ceiling there, and the lever is **more ADC bits or a smaller voltage range, not more shielding.**
   On a *driven* run the picture inverts: UL reaches **34×** its floor and AE **8×** (companion
   `RUN_20261002_ANALYSIS.md`), so the quantization ceiling only binds the floor, not the measurement.

## 4. Source-by-source
- **24 V switch-mode PSU — not a culprit (null).** Swapping to a linear lab supply moved every channel
  **1.00–1.03×** and did not touch the 1060.7 kHz line (0.00331 → 0.00336 V). The switch-mode supply is not
  a measurable noise source; there is no reason to keep a bench instrument permanently in the rig.
  *(blocks B0 → B2, B2A.)*
- **1060.7 kHz — instrument-side, three independent confirmations.** The line survived (a) the linear-PSU
  swap, (b) a **shorted SP probe tip** (block 0b — nothing connected, line still present), and (c) the drive
  being energized (+2.4 %). It is made in the scope + probe chain, is a constant under every run, and **no
  rig-supply / box / cabling work removes it** — characterise and subtract it. *(B0b, B2A, B3a.)*
  An external tachometer sitting near the cabling adds to this line's coupling, but the residual is
  instrument-side; the tachometer is the operator's speed instrument and **stays on** — record its presence
  in the run notes.
- **Heater/temperature control box — AE 126–135 kHz, bidirectional.** Switching the box off collapses AE's
  126–135 kHz structure **×0.51** (B2B); switching it back on restores it **×2.27** (B4b) — made and
  unmade. The box also couples into SP on its own (not only with an energized drive): with the drive
  mains-off, box on/off moves SP's 126–135 kHz band ~4× (B2C vs B2D). *(B2B, B4b, B2C, B2D.)*
- **Drive output stage — a step, not a ramp.** Decoupled (so vibration is excluded by construction), noise
  rises when the output stage is active but **does not scale with rpm**: 500 and 1500 rpm are 0.1 % apart on
  SP. So the drive's contribution is the output stage being *active*, not the frequency it runs at. This
  turns the 0035 coupled inference ("SP +43 % flat with speed") into a decoupled measurement. *(B5a–B5c.)*
- **Sinus (output) filter — only acts when the drive is driving.** Stationary it does nothing (0.98–1.02×).
  Running, removing it drops AE ~41 % and SP ~12 % — i.e. the filter *raises* the sensor noise. **But it
  must not be removed** (see §5). *(B5a/B5e vs B5b/B5f.)*
- **Filter–VFD ground — direction stands, magnitude pending a verified-rpm repeat.** Stationary the ground
  does nothing (5a vs 5h, 0.95–0.99×). *Running*, ground-ON is much worse and reversibly so: ground-off
  +71 % (5b) → ground-on +288 % (5i) → ground-off +91 % (5k). Block 5i carries an unverified rpm (the drive
  display read 0.00), but that doubt is **conservative** — less rotation cannot create more noise, and
  ground-ON *stationary* is only 0.0141, so 5i's 0.0544 required the output stage active. **One clean repeat
  at verified rpm is owed before any grounding scheme is designed.** Tracked in ticket 0048. *(B5b, B5h,
  B5i, B5k.)*
- **Heater relay — SP 50–100 kHz, within one run.** Toggled twice in one run: SP +29 % (OFF 0.0999 → ON
  0.1321 → OFF 0.1048), concentrated in 50–100 kHz (SP +90 %, AE +40 %). AE's *total* moved only +1.6 %
  while its band moved +40 % — a single RMS would have reported "nothing." *(B6.)*

## 5. The operating trade-off and recommendation
The **sensor-cleanest** configuration (no filter) and the **specimen-safest** configuration (filter fitted)
are opposites. The sinus filter limits dv/dt at the motor terminals and suppresses **bearing currents** —
the electrical erosion that pits bearing races. On a *bearing test rig* that is the thing we must not do to
the specimen under test; the erosion is slow, invisible, and indistinguishable from real mechanical
degradation. The filter–VFD ground was confirmed by Kim to be a **functional ground, not protective earth**
(2026-10-02), so there is no safety constraint forcing either ground state.

**Recommendation (interim, provisional until the verified-rpm ground repeat):**
- **Filter ON** — specimen integrity outranks sensor cleanliness; elevated sensor noise is a known,
  subtractable offset.
- **Functional ground OFF** — the quieter *running* configuration on the current (unverified-rpm) evidence.
- **Never run "no filter"** to clean up the sensors.
- If a quieter *floor* is genuinely wanted, the lever is **ADC resolution / voltage range** (§3.2), not
  regrounding or shielding.

## 6. A heated-run effect the ladder could not see
None of the 23 noise blocks heated the oil, so this appeared only on the 2026-10-02 13 h run
(`20261002_122423`). The heat's duty cycle moves the sensors, and **UL/AE and SP in opposite directions**:

    channel   heat FULL power   heat MODULATING at setpoint   ratio
    UL        0.06271           0.03010                       0.48x
    AE        0.02057           0.01447                       0.70x
    SP        0.09086           0.14498                       1.60x

UL/AE fall back to **exactly their 0046 floor** when the heat modulates, so the elevation at full power is
**acoustic, not electrical** (UL is an acoustic sensor; convection in heated oil is the plausible
mechanism) — which is why the electrical blocks never saw it. **SP is the opposite:** at full power the
relay stays closed, near setpoint it clicks continuously, and SP responds to the *switching* (the block-6
50–100 kHz path), not the current. A profile whose setpoint ramps ~5 °C/h modulates almost throughout —
worst case for SP, best for UL/AE. This does **not** undermine the UL-vs-temperature finding; heat *raises*
UL, so it masks the real temperature effect rather than creating it — and that temperature effect is itself
**band-dependent**, not a simple fall: at a fixed 1800 rpm over 45→100 °C, broadband UL rms falls only
~9 % (dominated by its 0–10 kHz band, which is ~99 % of UL), while **UL's 10–50 kHz band rises +46 % and
AE's 50–100 kHz nearly doubles (1.92×)** — the signature of a thinning film (less damping, more asperity
contact). So **report UL in bands, not rms, when the question is the oil film.** Full treatment, and the
check that this rise is 4.5× too large to be the heater, is in the companion `RUN_20261002_ANALYSIS.md`.

## 7. Open threads
- **Grounding magnitude (0048)** — one clean *running* ground-on/off pair at a **verified** rpm.
- **Drive command behaviour (0047)** — largely resolved: the drive stops on the first command; the
  apparent "won't stop" was a stop-loop watching a stale `frequency_out_hz` readback (the valid test is
  `rpm == 0` + a frozen pulse count). Remaining: readback lies (verify against the tach), the source mode
  falls back on a power cycle (checklist §3), the high-Hz start sequence is not fully modelled.
- **Two confirmatory reference blocks, after rig restore:** a 15-min 0 rpm acquire in the **actual
  operating configuration** (coupled, drive live, heater box on — no single block has that combination),
  and the verified-rpm ground pair above. Both close 0046.

## 8. Method lessons (what the retractions taught)
- **A band-integrated amplitude at a nominal frequency cannot tell a line from broadband**, and a
  "strongest lines" listing just picks the loudest random bin. A line is real only if the same frequency
  repeats across channels *and* runs — 1060.7 kHz does; the "SP 129/131 kHz line" did not (it was flat
  broadband).
- **Scattered scalars breed contaminated comparisons.** The ground "+288 %" was first over-read, then
  over-retracted, and only the uniform 23-block reference settled it (direction yes, magnitude pending).
  The uniform reference exists because of this.
- **A run that fails as a *block* can still be the *evidence* a finding rests on.** `..._SPLIT_...` is the
  in-run A/B that identified the external tachometer (the 1.06 MHz conclusion rests on it); `..._ABORTED_…`
  is the tachometer-on floor. Both were nearly discarded for their names. All 69 scope runs are now in
  `eceherning`, fault references included, each carrying its fault label as a sidecar.

## 9. Caveats
- Decoupled 5-series speeds are **commanded, not instrument-verified** (decoupled, the tach reads the rig
  shaft, not the motor); 500 and 1500 rpm cannot be distinguished in any series.
- Magnitudes near the floor are **quantization-limited** (§3.2) — read small broadband deltas with care.
- Figures in older per-block notes predate the uniform reduction; **§10 + the CSV are authoritative.**

## 10. Appendix — block → Azure run-id map
All at `eceherning/<run_id>/scope_<run_id>.h5`.

| block | configuration | run_id |
|---|---|---|
| B0 | bare floor, switch-mode PSU, drive off | `20260930_093141` (+ `_085938_SPLIT`, `_085412_ABORTED`) |
| B2A | linear 24 V PSU | `20260930_102402` |
| B0b | shorted SP probe input | `20260930_110822` |
| B2B | heater/temp box OFF | `20260930_112905` |
| B3a | VFD energized, motor still, sinus OFF | `20261001_084527` |
| B3b | motor 600 rpm, coupled (bearing signal) | `20261001_103916` |
| B5a / B5b / B5c | decoupled 0 / 500 / 1500 rpm, sinus ON | `20261001_113117` / `114015` / `114854` |
| B5e / B5f / B5g | decoupled 0 / 500 / 1500 rpm, sinus OFF | `20261001_125027` / `125757` / `130453` |
| B5h / B5i | decoupled 0 / 500 rpm, sinus ON, ground RESTORED | `20261001_133652` / `134851` |
| B5k | decoupled 500 rpm, ground removed again (reversibility) | `20261001_141121` |
| B4b | heater box back ON, drive energized, 0 rpm | `20261001_142438` |
| B6 | heater relay toggled twice, 0 rpm | `20261001_145326` |
| B2C / B2D | VFD mains off, box ON / box OFF, decoupled | `20261002_092610` / `20261002_100026` |
| 13 h run | operating run (heat duty-cycle finding, §6) | `20261002_122423` |

*Report generated 2026-10-02. Numbers are authoritative in `docs/0046_noise_floor.csv`; this prose is a
synthesis of ticket `TEAM/tickets/0046-electrical-noise-source-characterization.md`.*
