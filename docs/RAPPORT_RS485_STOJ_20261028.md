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

## Kan støjen fjernes bagefter, så valid data kan skilles fra støj? Ja.
- **Den ligger kun i toppen af SP-spektret**, 1-2,5 MHz, og vokser mod 2,5 MHz (+1 dB ved 1 MHz, +8 dB ved 2,25-2,5 MHz;
  ligner HF-støj, der foldes ned fra over samplingsgrænsen på 2,5 MHz). SP under 1 MHz er uændret (+0,8 dB), UL og AE
  uændret (total varians −0,05 / +0,07 dB).
- **Den betyder noget, hvis SP bruges bredbånd i stilstand:** SP-Vpp i stilstand 0,40 V (manuel) mod 1,46 V (RS485,
  berørte sweeps), rms 0,045 mod 0,068 V. Det er på størrelse med SP-Vpp ved 1176 rpm (1,33 V) og kan derfor se ud
  som rotationssignal. Under rotation ses ingen forskel (støjen drukner i slæberingens egen støj).
- **Afhjælpning:** lavpasfiltrér SP ved ca. 1 MHz (eller analysér kun SP-bånd under 1 MHz), så forsvinder forskellen;
  UL/AE kræver ingenting. Til at markere berørte sweeps i stilstand duer SP-effekt i 2-2,5 MHz over gulvet
  (RS485-kørsel: 15 af 30 stopsweeps; manuel: 0 af 28).

## Bliver UL/AE-signalet druknet? (signal over stilstandsgulv, `py/tools/rs485_compare/signal_over_floor.py`)
- **Gulvet er scopets egen kvantisering, ikke common-mode:** hvilevarians er kun 5,5 dB (UL) / 4,8 dB (AE) over ren
  kvantiseringsstøj (trin 2,0 mV UL, 20 mV AE). Dermed er "ingen RS485-støj på UL/AE" kun **ingen støj over scopets
  gulv**; common-mode under ca. 1 mV (UL) / 10 mV (AE) kan ikke ses med de nuværende områder.
- **Tydeligt over gulvet (≥ 15 dB ved ≥ 1800 rpm):** UL 0,5-20 kHz (20-50 dB), AE 10-200 kHz (16-34 dB).
- **Druknet / ved gulvet (≤ 3 dB):** UL over 50 kHz og under 500 Hz ved 600 rpm; AE under 10 kHz og over 500 kHz.
  AE ved 600 rpm kun 4-10 dB (20-200 kHz); AE 200-500 kHz først ved ≥ 1800 rpm (6-13 dB).
- **RS485 på/af ændrer det ikke** (signal over gulv inden for få dB i de to kørsler).
- UL-vinduet 0,4 V er ca. 2,6 × for bredt (max Vpp 0,15 V; hvilesignal 1,1 mV rms < ét ADC-trin på 2 mV): 0,2 V
  ville sænke gulvet 6 dB. AE kan ikke indsnævres (spidser op til 4,6 V Vpp).
