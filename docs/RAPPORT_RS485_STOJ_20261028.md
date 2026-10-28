# Konklusion: støj i testforløbet, manuel VFD-styring vs. RS485 (2026-10-28)

**Forsøg.** Samme 53 min temperatursweep (40-100 °C, fart-trappe 600-3000-600 rpm), samme leje og scope-indstillinger.
*Manuel* (`20261028_114027`): RS485 pillet af VFD'en, fordi den ses at give common-mode-støj. *RS485*
(`20261028_125638`): RS485 på VFD'en, drevet over Modbus. VFD-jord på i begge. Omron sad på bussen i begge, så forskellen
er kun VFD-siden. Data: Azure `csfbst001/eceherning/<run_id>/`. Detaljer: `docs/RS485_NOISE_COMPARISON_20261028.md`.

## Hvor er støjen mere / mindre (stilstand = ren test, bussen kører, intet roterer)
- **Mere med RS485: kun SP (slæbering) ved 1-2,5 MHz**, vokser mod 2,5 MHz: 1,0 / 1,7 / 3,6 / 4,1 / 1,0 × gulvet ved
  40 / 55 / 70 / 85 / 100 °C (manuel: fladt 1,0 ×). SP < 1 MHz uændret (+0,8 dB). SP-Vpp i stilstand 0,40 V → 1,46 V.
- **UL og AE: ingen støj over scopets gulv:** alle bånd 0-2,5 MHz inden for ±0,7 dB, ingen bursts, ingen linjer ved
  9600-baud-harmoniske eller VFD-bæreren (4,66 kHz). Total varians −0,05 / +0,07 dB.
- Under rotation er UL 6-20 kHz 2-4 dB lavere og AE 10-500 kHz 1-3 dB højere med RS485. Findes ikke i stilstand og
  RS485-kørslen kom efter den manuelle på samme leje: tilskrives lejets tilstand, ikke bussen.

### Forskel RS485 − manuel (dB, positiv = mere støj med RS485), settled data, middel over de 5 temperaturniveauer
`*` = signifikant (> 2 SE og > 1 dB).

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

Alle øvrige bånd på UL og AE i stilstand: inden for ±0,7 dB. Fuld tabel for alle 12 bånd:
`docs/RS485_NOISE_COMPARISON_20261028.md`.

### SP 1-2,5 MHz i stilstand, pr. temperaturniveau (× gulvet, median af stopsweeps)
| Niveau | 40 °C | 55 °C | 70 °C | 85 °C | 100 °C |
|---|---|---|---|---|---|
| Manuel (RS485 af) | 1,0 | 1,0 | 1,0 | 1,0 | 1,0 |
| RS485 på | 1,0 | 1,7 | 3,6 | 4,1 | 1,0 |

Støjen er jævn inden for hvert stop, men kommer og går mellem niveauerne; den følger ikke varmen (PV−SV ens i de to
kørsler). Spektral form (RS485-sweeps over gulvet mod manuel): +0,7 dB under 1 MHz, +1,0 ved 1-1,25 MHz, +2,8 ved
1,5-1,75, +5,1 ved 1,75-2,0 og +7,9 dB ved 2,25-2,5 MHz.

## Kan det skilles fra bagefter? Ja
SP-støjen sidder kun over 1 MHz: lavpasfiltrér SP ved ca. 1 MHz (UL/AE kræver ingenting). Berørte stopsweeps kan
markeres på SP-effekt i 2-2,5 MHz (RS485: 15/30, manuel: 0/28). Under rotation ses den ikke.

## Drukner UL/AE-signalet? Gulvet er scopets kvantisering
Hvilestøjen er kun 5,5 dB (UL) / 4,8 dB (AE) over ren kvantiseringsstøj (trin 2,0 / 20 mV). "Ingen RS485-støj" betyder
derfor ingen støj *over* gulvet; common-mode under ca. 1 mV (UL) / 10 mV (AE) kan ikke ses med nuværende områder.
Signal over gulv ved ≥ 1800 rpm: **UL 0,5-20 kHz 20-50 dB, AE 10-200 kHz 16-34 dB**. Druknet (≤ 3 dB): UL > 50 kHz,
AE < 10 kHz og > 500 kHz; AE ved 600 rpm kun 4-10 dB. RS485 på/af ændrer det ikke. UL-vinduet 0,4 V er ca. 2,6 × for
bredt (max Vpp 0,15 V): 0,2 V ville sænke gulvet 6 dB. AE kan ikke indsnævres (spidser 4,6 V Vpp).

## Forbehold og næste skridt
n = 1 pr. betingelse, ingen ombytning af rækkefølge. Næste: stilstandstest med fint område på UL/AE, RS485 på/af, for
at se hvad der ligger under gulvet. Scripts: `py/tools/rs485_compare/`.
