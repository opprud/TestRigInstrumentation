# Run 2: slæberings-tvillingen `20261110_100301` (Keratech 22, 14 kg, slæbering løftet)

Kørt 2026-11-10 10:03 -> 2026-11-11 00:18 (855 min, `duration_reached`). 4273 sweeps gemt, **0 skippede**, 162 OE-captures,
heartbeat 1707 sendt / 0 fejlet. Heater guard: `VERIFIED channel 0 OFF` 00:23; Omron PV faldt 92 -> 84 C inden for 2 min.
Azure: konto `csfbst001`, container `eceherning`, blob `20261110_100301/scope_20261110_100301.h5`, 3 778 661 752 B, MD5 7181c0c013dd66effafa4b4f9cf14bc3 (verificeret størrelse + MD5), plus 4 sidecars.
h5 `/metadata`: `bias_v 0.0`, `slip_ring "lifted"`, `clamp_load_kg_measured 14.53`.
Analyse: `py/tools/sliptwin_analysis.py` (hver 3. sweep, 1425 pr. kørsel, run 1 = `20261109_114623`).

## SP uden bias
- SP-middel: **-0.015 V** (min -0.018, max -0.013) i hele kørslen. Run 1: 0.989 V (bias til stede; 0.08 V i sweeps hvor akselvinklen mistede kontakt).
- AC-rms, 0 rpm: **0.0100 V** ved alle temperaturer 30-100 C (run 1: 0.012-0.026, varierer med varmerelæets skift).
- AC-rms, 1800 rpm: 0.0125 V; 3000 rpm: 0.0121 V. Altså **kun +20 % fra 0 til 1800 rpm og så fladt** (run 1: 0.016, 0.015). SP uden bias er næsten ren opsamling, ingen tydelig rotationsrespons.
- Båndene 10-50 / 50-100 kHz: 0.0011-0.0013 V, uændret med fart og temperatur (run 1: 0.0013-0.0024, mere varierende).
- Konklusion: løftet slæbering gør SP stille og temperaturuafhængig (relæ-skiftestøjen i run 1 forsvinder); SP er så en støjreference, ikke et lejesignal.

## Påvirker slæberingen UL/AE?
Nej, ikke målbart som støjvej. 0 rpm-gulv: UL rms 0.0010 V i begge kørsler; AE 0.0120-0.0127 V (run 1: 0.0125-0.0135), samme niveau.
Ved fart ligger UL (0.014-0.022 V) og AE (0.03-0.14 V) i samme størrelsesorden som run 1; AE stiger med temperatur i begge (1800 rpm, 10-50 kHz: 0.015 -> 0.041 V i run 2, 0.011 -> 0.036 V i run 1). Forskellene er inden for run-til-run-variation (én kørsel hver, så ikke testet statistisk).

## Last mass_g(T)
- Median pr. temperaturbin, run 2 (kg): 30 C 15.6, 40 C 15.3, 50 C 15.3, 60 C 15.5, 70 C 15.7, 80 C 16.0, 90 C 16.2, 100 C 16.3. Stigning ca. +1.0 kg (+7 %) fra 50 til 100 C.
- Run 1: 16.2 -> 18.5 kg (+14 %) over 30 -> 100 C. Run 2 drifter altså mindre, men starter også lavere (14.55 kg efter nulstilling).
- Ved run-slut 15.7 kg (varm). Start 14.55 kg -> **netto +1.2 kg** over kørslen.
- **Cool-down (00:19-06:30, 84 -> 23 C):** lasten stiger først til **16.00 kg ved 33 C (01:00)**, altså efter at temperaturen næsten er nede, og aftager så langsomt med en tidskonstant på timer: 15.96 (01:20), 15.87 (02:00), 15.80 (03:00), 15.75 (04:30), **15.73 kg kold kl. 06:30** (PV 23 C). Lasten følger ikke temperaturen ned, den halter timer efter. Det passer på sætning/hysterese/celle-termisk lag, ikke på øjeblikkelig udvidelse i klemmen (den ville falde med T).
- **Permanent rest:** kold efter kørslen 15.73 kg mod 14.55 ved start = **+1.2 kg (+8 %) varigt**, som i run 1 (17.24 kold mod 14.5). Årsagen (celle-nulpunkt, der har flyttet sig, eller klemmen, der har sat sig) er stadig uafklaret; den løsnede-klemme-måling kold afgør det: viser cellen et nul-skift, er det cellen.
- Brug `mass_g(t)` i analysen. Kurve: `py/data/runs/20261110_100301/cooldown_load_20261110_100301.csv` (30 s).

## Sweeps / overshoot
4273/4275 planlagte sweeps gemt, 0 skippede, 0 reset. PV lå 0-2 C over SV under opvarmning (fx 72/70, 77/75, 87/85, 91/90) og 1 C under ved 99/100. Hastigheden fulgte trinene inden for 5 rpm.
