# Manuel VFD-styring vs. RS485: hvor er støjen mere eller mindre?

**2026-10-28** · Detaljer og metode: `docs/RS485_NOISE_COMPARISON_20261028.md` · scripts `py/tools/rs485_compare/`

## Forsøg
Samme 53 min temperatursweep (40-100 °C, fart-trappe 600-3000-600 rpm), samme leje, samme scope-indstillinger, VFD-jord på.

| | A: manuel | B: RS485 |
|---|---|---|
| VFD | styret med hånden, RS485 **af** VFD | styret over Modbus, RS485 **på** VFD |
| Azure (`csfbst001/eceherning/`) | `20261028_114027/` | `20261028_125638/` |

Omron sad på bussen i begge; forskellen er kun VFD-siden.

## Forskel B − A (dB, positiv = mere støj med RS485), settled data, middel over de 5 temperaturniveauer
`*` = signifikant (> 2 SE og > 1 dB). Stilstand er den rene test (bussen kører, intet roterer).

| Kanal / bånd | 0 rpm | 600 | 1200 | 1800 | 2400 | 3000 |
|---|---|---|---|---|---|---|
| UL 6-10 kHz | 0,0 | −4,0* | −3,6 | −3,7* | −2,3 | −2,5 |
| UL 10-20 kHz | 0,0 | −1,9* | −2,3 | −2,8* | −1,8 | −1,9 |
| UL 50-100 kHz | −0,1 | +0,2 | −0,1 | −0,2 | −0,1 | −0,1 |
| AE 20-50 kHz | 0,0 | +1,8 | +1,6* | +0,9 | +2,7* | +2,9* |
| AE 200-500 kHz | +0,1 | +0,1 | +0,7 | +0,7 | +2,1* | +2,4* |
| SP 0-500 Hz | −0,7 | +0,1 | −1,7 | −1,3 | −2,9 | −3,5 |
| SP 3-6 kHz | −0,1 | −0,3 | −1,0 | −1,4 | −4,2 | −3,0 |
| SP 1-2,5 MHz | **+2,8*** | +0,8 | +0,6 | +0,3 | +0,1 | 0,0 |

Alle øvrige bånd på UL og AE ved stilstand: inden for ±0,7 dB.

## Hvor er det mere / mindre
- **Mere med RS485:** kun **SP ved 1-2,5 MHz i stilstand**: 1,0 / 1,7 / 3,6 / 4,1 / 1,0 × gulvet ved 40 / 55 / 70 / 85 / 100 °C
  (manuel: fladt 1,0 ×). Common-mode, men langt over AE-båndet (< 500 kHz).
- **Uændret:** UL og AE i stilstand, alle bånd 0-2,5 MHz; ingen bursts; ingen linjer ved 9600-baud-harmoniske
  (4,8 / 9,6 kHz) eller VFD-bæreren (4,66 kHz).
- **Anderledes under rotation, men ikke fra bussen:** UL 6-20 kHz **mindre** (−2…−4 dB), AE 10-500 kHz **mere**
  (+1…+3 dB ved 2400-3000 rpm), SP bredbånd mindre. Findes ikke i stilstand, hvor bussen kører lige så meget, og
  B kørte efter A på samme leje (indkøring).

## Konklusion
Med VFD-jord på giver RS485 på VFD'en **ingen målbar ekstra støj på UL og AE**; kun slæberingen (SP) får en svag,
ujævn HF-stigning. Forbehold: n = 1 pr. betingelse, uden ombytning af rækkefølge.
