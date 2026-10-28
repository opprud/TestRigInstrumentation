# Rapport: Bidrager RS485 på frekvensomformeren (VFD) med støj til sensorerne?

**Dato:** 2026-10-28 · **Rig:** ForeverBearing testrig (lejetest, UL / AE / SP på scope) · **Detaljer:** `docs/RS485_NOISE_COMPARISON_20261028.md`

## Spørgsmål
Kan RS485-kablet til VFD'en (Modbus-trafik og kablets jordsti) give støj på ultralyd (UL), akustisk emission (AE)
og slæbering (SP)? Observeret tidligere: kraftig common-mode-støj med kablet i, kraftigt reduceret uden.

## Forsøg
To identiske kørsler, 53 min, samme leje (smurt), samme scope-indstillinger, VFD-jord på i begge.
Fem oliepunkter (40, 55, 70, 85, 100 °C), hver med én fart-trappe 600-3000-600 rpm og et stop.

| | A: RS485 **af** VFD | B: RS485 **på** VFD |
|---|---|---|
| Drev | styret manuelt | styret over Modbus af testprogrammet |
| Data (Azure `csfbst001/eceherning/`) | `20261028_114027/` | `20261028_125638/` |

Omron-temperaturregulatoren sad på bussen i begge, så forskellen er kun VFD-siden. Analyse: effektspektre pr. sweep,
sammenlignet pr. (hastighed, temperaturniveau); stilstand er den rene test, da bussen kører, men intet roterer.

## Resultat
1. **UL og AE: ingen målbar forskel ved stilstand** (alle bånd 0-2,5 MHz inden for ±0,7 dB). Ingen bursts, ingen
   linjer ved 9600-baud-harmoniske eller VFD-bæreren (4,66 kHz).
2. **SP: lille, ujævn stigning ved 1-2,5 MHz ved stilstand** med RS485 på: 1,0 / 1,7 / 3,6 / 4,1 / 1,0 × gulvet ved
   40 / 55 / 70 / 85 / 100 °C (RS485 af: fladt 1,0 ×). Common-mode-signatur, men langt over AE-båndet (< 500 kHz) og
   uden virkning på UL/AE. Årsag til niveau-afhængigheden er uafklaret.
3. **Forskelle under rotation** (UL 6-20 kHz −2…−4 dB, AE 10-500 kHz +1…+3 dB i B) findes ikke ved stilstand og
   tilskrives **ikke** RS485, men lejets tilstand: B kørte efter A på samme leje.

## Konklusion
Med VFD-jord på **tilfører RS485-kablet ikke målbar støj til UL og AE**; den voldsomme common-mode-støj skyldtes
sandsynligvis manglende jord og er ikke med i data. Kun slæberingen (SP) viser en svag HF-effekt uden betydning for
analysen. RS485 kan forblive tilsluttet under målinger.

## Forbehold og næste skridt
- n = 1 pr. betingelse, og ingen ombytning af rækkefølge: rotations-forskellene kan ikke afgøres uden en tredje kørsel
  (B før A, eller B igen).
- Frekvensen i A er sat manuelt (±1 %, værst +4 % ved 10 Hz); `rpm_meas` fra tachoen er hastigheden af record.
- Ved SP-effekten: gentag ved stilstand ved 55-85 °C, evt. med/uden RS485-kabel koblet midt i en kørsel, for at
  fastslå årsagen.
