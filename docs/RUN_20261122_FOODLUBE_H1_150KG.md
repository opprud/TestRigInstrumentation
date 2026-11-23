# Test 9 — Foodlube H1 Power 22, ~150 kg (estimat), slip ring tilsluttet, 1 V bias

Run `20261122_123912`, 2026-11-22 12:39 → 2026-11-23 02:54 (855 min). Azure: `eceherning/20261122_123912/`, MD5 4a717f4713ddde72dfd79bd6025bfd5e (4,048,594,258 B), verificeret; sidecars ok.

## Forløb
- 4273 sweeps, **0 sprunget over**, ingen scope-reset. Staircase fulgt (rpm inden for ca. 1 % af mål), PV fulgte SV (max PV 100 °C; ingen >105).
- SP-middel 0,99 V = bias til stede hele vejen. Gulv (0 rpm, varm): UL 0,0010 V, AE 0,0116 V — som run 5 og Test 8.
- Heater guard: OFF verificeret 02:57; PV 93 → 39 °C på ca. 30 min.
- Klemmelast **ikke målt** (cellen over 74 kg-loftet, ERR 21): anker 69,5 kg + 4 blinde omgange ≈ 140 kg, standardiseret 150 kg, ±30 %.
- OE-sensor: afbrydelser ("Device disconnected unexpectedly") i loggen, ikke fatale.

## Sammenligning (AE/UL rms, V; 2–4 sweeps pr. celle, stride 3, afviger typisk ±20 % mellem celler)
| rpm / °C | AE run 5 (Keratech) | AE Test 8 (H1, 60 kg) | AE Test 9 (H1, 150 kg) | 9 vs 5 | UL 9 vs 5 |
|---|---|---|---|---|---|
| 1800 / 40 | 0,065 | 0,035 | 0,043 | −35 % | −10 % |
| 1800 / 70 | 0,071 | 0,053 | 0,061 | −14 % | −9 % |
| 1800 / 100 | 0,078 | 0,087 | 0,097 | +26 % | +26 % |
| 2960 / 70 | 0,169 | 0,075 | 0,127 | −25 % | −10 % |
| 2960 / 100 | 0,223 | 0,156 | 0,185 | −17 % | −1 % |
(2960/40 mangler i Test 9: for få afsluttede sweeps ved SV 40 og høj hastighed.)

## Konklusion
H1 ved ~150 kg ligger **−35 % til +26 %** fra Keratech 22 (run 5) i AE, uden ensartet fortegn: lavere ved 40–70 °C og høj hastighed, højere ved 1800 rpm/100 °C. UL er −10 til −1 % undtagen +26 % ved 1800/100. Det er ikke et robust fald som ved 14 kg (−14 til −43 %), og Test 8 (60 kg) viste heller ingen. H1-forskellen er derfor ikke et stabilt, lastuafhængigt fald i AE; det kan være last- eller run-til-run-spredning, og med 2–4 sweeps pr. celle og en ±30 % usikker last kan vi ikke skelne. Gulve og rpm-opførsel er uændrede. Test 9 er gennemført rent og kan indgå i matrixen.
Caveat: kun stride-3 bånd/rms; ingen separat analyse af temperaturdrift i last (ikke målt).

Kold løsnet nul-aflæsning: afventer at Kim løsner klemmen.
