# Does RS485 on the VFD add noise? Runs 20261028_114027 (off) vs 20261028_125638 (on)

Same 53 min temperature sweep, same scope settings, same bearing, VFD earth connected in both. **A** = RS485 unplugged
from the VFD, drive run by hand (`docs/RUN_20261028_MANUAL_SWEEP.md`). **B** = RS485 on the VFD, runner polling and
driving it (`docs/RUN_20261028_MODBUS_SWEEP.md`). Data: Azure `csfbst001/eceherning/<run_id>/`.
Note the **Omron stayed on the bus in both runs**, so what differs is the VFD side only (its cable, its ground path, the
status/frequency traffic), not the bus as such.

Method: per sweep and channel, Welch PSD (65,536 pts, 76 Hz resolution) and 1 ms frame energies; sweeps classed by
tacho speed bin (0 / 600 / 1200 / 1800 / 2400 / 3000 rpm) and by SV level, settled only (|PV-SV| <= 5 C); delta = median
band power B / A per (speed, SV) cell, averaged over the 5 levels. Scripts: `py/tools/rs485_compare/` (`extract.py` first).

## Result
**At standstill - the clean test, no mechanical noise, bus traffic still running - UL and AE are indistinguishable:**
every one of 12 bands (0 Hz-2.5 MHz) within +-0.7 dB. No bursts (1 ms frame energy max/median 3.0 vs 3.0, same fraction
of sweeps >3x). No lines at the 9600-baud harmonics (4.8 / 9.6 / 14.4 / 19.2 kHz) or the 4.66 kHz VFD carrier, all < 1 dB
over the local floor in both runs. **RS485 on the VFD does not measurably raise UL or AE noise once the earth is on.**

**SP (slip ring, a high-impedance antenna) is the only channel that moves, and only 1-2.5 MHz at standstill:**

| SV level | A (RS485 off) | B (RS485 on) |
|---|---|---|
| 40 C | 1.0x | 1.0x |
| 55 C | 1.0x | 1.7x |
| 70 C | 1.0x | 3.6x |
| 85 C | 1.0x | 4.1x |
| 100 C | 1.0x | 1.0x |

(median band power at the 0 rpm stops, relative to the floor 1.17e-3 V^2). A is flat to +-0.1 at every stop; B is steady
within a stop minute but comes and goes between levels. Does not follow the heater (PV-SV identical in both). This is the
common-mode signature Kim saw on the scope with the cable fitted, but with the earth on it is small, intermittent, and
**far above the AE band (< 500 kHz)**; UL/AE do not see it. Cause of the level dependence is unexplained.
At 600 rpm SP 1-2.5 MHz is x4-10 higher in *both* runs (slip-ring contact noise), which hides the bus effect there.

## Differences under rotation - NOT attributed to RS485
UL 6-20 kHz is 2-4 dB lower in B at 600-1800 rpm; AE 10-500 kHz is 1-3 dB higher in B at 2400-3000 rpm; SP broadband
about -3 dB at 2400-3000 (within its 2-4 dB cell scatter). They are absent at 0 rpm where the bus traffic is identical,
and within-run up/down repeatability is only 0.4-0.7 dB, so they are real but point at bearing state (B ran second on the
same bearing: run-in or film) and a 0-4 % difference in operator-set speed in A, not at electrical coupling. **n = 1
per condition and no order swap, so this cannot be settled without repeating in the opposite order.**

## Lines present in both runs (not bus noise)
UL 1.07 kHz at standstill, +6-7 dB over floor in both (the "1 kHz line", ticket 0040; gone as soon as the shaft turns, so
motor-off vs motor-on cannot discriminate it). AE 344 kHz at standstill, intermittent in both and ~3 dB stronger in B at
matched heater state; it follows the heater (stronger with the heater off, PV above SV).
