# Run 20261118_082907 — Test 6: Keratech 22, ~142 kg ESTIMAT ("150 kg"), slæbering LØFTET, bias 0

Start 2026-11-18 08:29, slut 22:44 (duration_reached). 4273 sweeps, 0 skippede, 166 OE-captures. Varme: guard VERIFIED OFF 22:48, PV 29 °C ved 23:38.
Klemme: anker 66,3 kg + 4,25 blinde drej (~17,8 kg/drej), ±30 %; mass_g er null (cellen over ~74 kg loft). Lejet smurt før start.
Azure: eceherning/20261118_082907/ (h5 3 843 601 976 B, MD5 9d2a55251ea8 verificeret). Lokal h5 slettet.
Metadata bekræftet i h5: bias_v 0.0, slip_ring lifted, clamp_load_kg 150, last_measured 66.3, turns 4.25.

## Sammenligning (middel rms, V; samme rpm/temperatur)
| punkt | run | UL | AE | SP | AE 50-100k |
|---|---|---|---|---|---|
| 1800 rpm/100 °C | 2 (14 kg twin) | .0139 | .065 | .0126 | .037 |
| | 4 (60 kg twin) | .0114 | .066 | .0127 | .036 |
| | 6 (150 kg twin) | .0079 | .070 | .0126 | .043 |
| | 5 (150 kg bias) | .0066 | .078 | .0227 | .049 |
| ~2960 rpm/100 °C | 2 | .0141 | .121 | .012 | .075 |
| | 4 | .0158 | .133 | .012 | .075 |
| | 6 | .0123 | .164 | .012 | .098 |
| | 5 | .0109 | .223 | .021 | .133 |
| 0 rpm 40/100 °C | alle | .0010 | .011-.013 | .010 | — |

## Konklusion
- AE stiger med last også uden slæbering (0,121 -> 0,133 -> 0,164 V ved 2960/100 °C); UL falder med last. Samme mønster som bias-runs, så det er lejet, ikke slæberingen.
- Run 6 ligger lavere end run 5 (AE ~26 % ved 2960 rpm): kan være lidt lavere faktisk klemmelast (estimat ±30 %) eller slæberingens bias/kontakt. Kan ikke adskilles af denne kørsel.
- SP uden bias er flad (0,012-0,013 V), uafhængig af last/hastighed: slæberingen er ikke en støjvej til UL/AE.
- Støjgulv ved 0 rpm uændret på tværs af runs 1-6.
- Støjcheck 08:57 (tick ~1680 s, 2590 rpm, 32 °C): UL/AE/SP glatte, ingen spring; AE 0,075-0,079 V på vej op, 0,079-0,094 på vej ned ved samme rpm — inden for normal spredning. Ingen påvirkning fundet (strided analyse, hver 3. sweep).
- Mangler: kold løsnet nul-aflæsning (før −330 g).
