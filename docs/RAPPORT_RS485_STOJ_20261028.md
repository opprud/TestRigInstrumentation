# Konklusion: støj i testforløbet, manuel VFD-styring vs. RS485 (2026-10-28)

Samme 53 min temperatursweep (40-100 °C, fart-trappe 600-3000-600 rpm), samme leje og scope-indstillinger.
**Manuel kørsel** (`20261028_114027`): RS485 pillet af VFD'en, fordi den ses at introducere common-mode-støj; drevet
styret med hånden. **RS485-kørsel** (`20261028_125638`): RS485 på VFD'en, drevet styret over Modbus.
Data i Azure `csfbst001/eceherning/<run_id>/`. Omron sad på bussen i begge; forskellen er kun VFD-siden.
Detaljer: `docs/RS485_NOISE_COMPARISON_20261028.md`.

## Konklusion
- **Manuel kørsel er den rene reference.** Med RS485 af VFD'en er SP ved 1-2,5 MHz i stilstand helt fladt (1,0 × gulvet
  ved alle fem temperaturniveauer).
- **Med RS485 på VFD'en ses common-mode-støj på SP (slæberingen) ved 1-2,5 MHz i stilstand**: 1,0 / 1,7 / 3,6 / 4,1 / 1,0 ×
  gulvet ved 40 / 55 / 70 / 85 / 100 °C, jævn inden for hvert stop men ujævn mellem niveauerne.
- **UL og AE påvirkes ikke målbart** i stilstand: alle bånd 0-2,5 MHz inden for ±0,7 dB, ingen bursts, ingen linjer ved
  9600-baud-harmoniske eller VFD-bæreren (4,66 kHz).
- Under rotation er UL 6-20 kHz 2-4 dB lavere og AE 10-500 kHz 1-3 dB højere i RS485-kørslen. Det findes ikke i
  stilstand, hvor bussen kører lige så meget, og RS485-kørslen kom efter den manuelle på samme leje, så det tilskrives
  ikke RS485.
- Forbehold: n = 1 pr. betingelse, ingen ombytning af rækkefølge.
