# Run 20261119_102430 — Test 7: Foodlube H1 Power 22, 14 kg (målt), slæbering tilsluttet, bias 1 V

Start 2026-11-19 10:24:30, slut 2026-11-20 00:39 (duration_reached). 4273 sweeps, 0 skippede, 167 OE-captures. Varme slukket af guard (VERIFIED OFF 00:43); PV 54 °C kl. 00:53.
Leje renset med sprit og smurt med H1 Power 22 (to korte forkørsler før: 2 min smøring, 5 min smoke). Klemme 14,53 kg målt ved start. Foodlube-metadata (base_oil, additiver, flash point, ml, dato, batch) er stadig FILL IN i h5.
Azure: eceherning/20261119_102430/ (h5 3 839 109 170 B, MD5 3cc6ef74f9b8 verificeret). Lokal h5 slettet. Metadata i h5: bias_v 1.0, slip_ring connected, clamp 14 kg.

## Sammenligning mod run 1 (Keratech 22, 14 kg, bias; rms V, middel pr. rpm/temp)
| punkt | UL run1 / run7 | AE run1 / run7 | SP run1 / run7 | AE 50-100k run1 / run7 |
|---|---|---|---|---|
| 0 rpm 100 °C | .0010 / .0010 | .0130 / .0115 | .035 / .0115 | .0020 / .0017 |
| 200 rpm 30 °C | .0011 / .0011 | .0128 / .0110 | .0157 / .0172 | .0019 / .0016 |
| 600 rpm 40 °C | .0026 / .0029 | .0136 / .0117 | .0178 / .0172 | .0027 / .0022 |
| 1800 rpm 40 °C | .0148 / .0159 | .0282 / .0242 | .0161 / .0161 | .0167 / .0145 |
| 1800 rpm 70 °C | .0130 / .0115 | .0419 / .0299 | .0166 / .0164 | .0239 / .0191 |
| 1800 rpm 100 °C | .0135 / .0085 | .0536 / .0340 | .0175 / .0173 | .0333 / .0236 |
| 2960 rpm 40 °C | .0200 / .0170 | .0493 / .0478 | .0151 / .0152 | .0319 / .0302 |
| 2960 rpm 100 °C | .0140 / .0113 | .1150 / .0659 | .0159 / .0161 | .0737 / .0482 |

## Observationer
- H1 Power 22 giver lavere AE end Keratech 22 ved samme rpm/temperatur, og forskellen vokser med temperaturen og hastigheden: ca. −10 % ved 40 °C/1800 rpm, −37 % ved 100 °C/1800 rpm og −43 % ved 100 °C/2960 rpm (AE rms). UL er også lavere ved 100 °C (−37 % ved 1800 rpm).
- 0 rpm-gulv uændret (UL 0,0010, AE 0,011-0,012). SP 0,016-0,017 V ved fart med bias, som run 1.
- Lyd ved lav hastighed (Kim, 10:26-10:35, ~100-300 rpm): kuglen "svupper". I rms/baand ved 200-300 rpm og 30 °C ligger UL og AE på run 1's niveau eller lavere (AE 0,0110 mod 0,0128), ingen forhøjelse. Periodicitet/envelope og OE-capture er IKKE analyseret (h5 slettet efter upload; ligger i Azure).
- Slæberingens bias gik tabt i de to første sweeps ved stilstand (SP-middel −0,02 V, tick 32 og 68), men var 0,99 V fra første bevægelse og hele resten af kørslen.
- Last (cellen, mass_g, målbar ved 14 kg): 14,5 kg ved start, 16,4 kg ved 100 °C/slut (+13 %). Samme mønster som runs 1-2 (drift op med temperatur); cellen er kun temperaturkompenseret til 50 °C. Cool-down-loggeren viste 16,4 kg kl. 01:53 med klemmen stadig stram.
- Temperatur: overshoot ved første opvarmning 9 °C (PV 39 mod SV 30) og 8 °C ved trinnet til SV 40; ellers PV følger SV inden for 1-4 °C.

## Åbent
- Kold løsnet nul-aflæsning (før: −351 g d. 19/11).
- Foodlube-metadata skal rettes (batch, ml, dato mm.).
- Envelope-/OE-analyse af lyden ved lav rpm hvis det ønskes (kræver h5 fra Azure).
