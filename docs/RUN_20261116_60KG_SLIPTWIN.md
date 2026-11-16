# Run 4 — `20261116_082654` — Keratech 22, 60 kg, slæbering LØFTET, bias 0

2026-11-16 08:26 -> 22:42 (855 min). Slæbering løftet og 1 VDC slukket af Kim før start; samme leje og smøring som run 3 (2 min @ 10 Hz Keratech 22 ekstra før start). Klemme 60,45 kg kold, 60,94 kg ved start (`clamp_load_kg_measured 60.94`). Kold løsnet nul før: **-389 g** (16/11 08:18). Azure: `csfbst001/eceherning/20261116_082654/`.

## Kørsel
- 4273 sweeps gemt, **0 skippede**; 158 OE-captures; heartbeat 1707 sendt, 0 fejl. Heater guard OFF verificeret 22:44.
- Metadata i h5 bekræftet: `bias_v 0.0`, `slip_ring lifted`, `clamp_load_kg 60`, `clamp_load_kg_measured 60.94`.
- Kold start: PV overshoot +9 °C over SV 30 (som run 3). Cool-down-loggeren startede ikke selv; startet manuelt 22:44 (PV 82 °C), 7 h.

## Slæbering (SP)
- SP mean median -0.016 V, 100 % af sweeps < 0.5 V = ingen bias hele vejen (som run 2). SP AC rms (V): 0 rpm 0.010 / 0.010 / 0.010 (30/60/95 °C); 1800 rpm 0.012-0.013; 3000 rpm 0.012. **Identisk med run 2 (14 kg)**: SP er stille og flad mod hastighed, temperatur og last. Med bias (run 3) var rms 0.012-0.026 og steg med temperatur — den ekstra rms er altså bias/slæbering, ikke lasten.

## UL / AE: 60 kg løftet mod 14 kg løftet (run 2) og 60 kg med bias (run 3)
- UL (rms V, 1800 rpm 30/60/95 °C): run 4 0.016/0.011/0.012; run 3 0.016/0.011/0.012; run 2 0.019/0.016/0.015. Run 4 = run 3 -> slæberingen påvirker ikke UL; 60 kg giver lidt lavere UL ved 60-95 °C end 14 kg.
- AE (rms V, 3000 rpm 30/60/95 °C): run 4 0.071/0.064/0.135; run 3 0.062/0.068/0.146; run 2 0.055/0.056/0.133. 1800 rpm 95 °C: 0.080 / 0.065 / 0.067. AE ligger ca. +10-25 % over 14 kg ved lav/mellem temperatur, og run 4 ≈ run 3 inden for sweep-scatter -> **ingen slæbering-effekt på AE**, last-effekten er lille.

## Klemmelast (`mass_g`, median ved >500 rpm)
- 30 °C 61.4; 50 °C 61.9; 70 °C 62.4; 90 °C 62.3; 100 °C 62.2 kg -> **+1.3 % over 70 K** (run 3: +3.7 %, run 2 +7 %, run 1 +14 %). Mindre drift end i run 3: lejet/stakken er nu sat.
- Cool-down: se `cooldown_load_20261116_082654.csv` (59.8 kg ved 82 °C kl. 22:44 ved start af loggeren; kold slutværdi opdateres).
- Kold løsnet nul EFTER: afventer Kim.

## Konklusion
Run 4 er rent gennemført (0 skippede, bias 0, løftet, alt arkiveret). Twin-testen ved 60 kg bekræfter run 2: slæberingen er ikke en støjvej til UL/AE, og SP er kun stille uden bias. Last 14 -> 60 kg giver en moderat AE-stigning, mens UL er stort set uændret. Klemmelastens temperaturdrift aftager med gentagne kørsler (+14 % -> +7 % -> +3.7 % -> +1.3 %), konsistent med setning/kryb i stakken.
