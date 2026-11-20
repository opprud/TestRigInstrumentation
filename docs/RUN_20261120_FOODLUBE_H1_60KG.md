# Run 20261120_092036 — Test 8: Foodlube H1 Power 22, 60 kg (målt), slæbering tilsluttet, bias 1 V

Start 2026-11-20 09:20:36, slut 23:35:38 (duration_reached). 4273 sweeps (sidste "Sweep 4273/4275"), 0 skippede, 164 OE-captures (OE havde enkelte udfald, normalt). Varme slukket 23:35 manuelt, PV 100 -> 87 -> 82 °C på 2 min, 29 °C kl. 00:35. 2 heartbeat-timeouts til VPS-watchdog (ikke kritiske).
Leje smurt med H1 Power 22, overskydende olie tørret af. Smoke 8 (5 min, `20261120_091333`): ingen klip, scop som frosset, bias 0,99 V. Klemme: 60,9 kg efter spænding, 58,7 efter smøring, 60,03 lige før start; i kørslen 58,6–62,5 kg (59,3 ved 30 °C, 59,1 ved 60 °C, 60,9 ved 100 °C, dvs. næsten ingen temperaturdrift mod +13 % i Test 7). Load-gain låst på 64. SP-middel 0,985–0,993 V i alle sweeps (bias hele vejen).
Foodlube-metadata: kemi fra TDS (arkitekten), application_date 2026-11-20; quantity_applied_ml og batch_number er FILL IN.
Azure: eceherning/20261120_092036/ (h5 4 002 548 933 B, MD5 a3dc40315256 verificeret). Lokal h5 ligger stadig (til envelope-analyse).

## Sammenligning mod run 3 (Keratech 22, 60 kg, bias, 61,9 kg median; rms V, median af afsluttede sweeps, n=1–7 sweeps pr. celle)
| punkt | AE run3 / run8 | Δ | UL run3 / run8 | Δ |
|---|---|---|---|---|
| 600 rpm 40 °C | .0118 / .0122 | +3 % | .0028 / .0035 | +24 % |
| 600 rpm 100 °C | .0138 / .0149 | +8 % | .0034 / .0035 | +2 % |
| 1800 rpm 40 °C | .0345 / .0356 | +3 % | .0131 / .0131 | 0 % |
| 1800 rpm 70 °C | .0387 / .0543 | +40 % | .0104 / .0116 | +12 % |
| 1800 rpm 100 °C | .0691 / .0867 | +26 % | .0119 / .0103 | −14 % |
| 2960 rpm 40 °C | .0628 / .0632 | +1 % | .0194 / .0180 | −7 % |
| 2960 rpm 70 °C | .0776 / .0747 | −4 % | .0168 / .0156 | −8 % |
| 2960 rpm 100 °C | .1632 / .1556 | −5 % | .0165 / .0146 | −11 % |
0 rpm / 30 °C: AE .0109 / .0113, UL .0010 / .0010 (støjgulv uændret). 90/190/290 rpm / 30 °C: AE 0,0115–0,0117 mod 0,0111–0,0113 (run 3), ingen forhøjelse.

## Konklusion
- **H1-effekten fra Test 7 (14 kg: AE −14/−29/−37 % ved 1800 rpm, −43 % ved 2960/100 °C) gentages IKKE ved 60 kg.** Ved 60 kg ligger H1 på ±5 % af Keratech ved 2960 rpm og 600 rpm, og ved 1800 rpm 70/100 °C er AE endda 26–40 % HØJERE. UL er ens eller lidt lavere (−7 til −14 %).
- Test 7's forskel ved 14 kg kan altså ikke generaliseres til "H1 er akustisk lavere". Enten er den load-afhængig (forsvinder ved 60 kg), eller også var den normal spredning mellem kørsler (n=1 pr. celle). Med cellerne her (1–7 sweeps) kan det ikke afgøres; 150 kg bliver tredje punkt.
- Hvis det er spredning mellem kørsler, er ±30–40 % på AE ved 1800 rpm/70–100 °C en realistisk usikkerhed ved én kørsel pr. olie og last.
- Lasten drev næsten ikke med temperaturen i denne kørsel (+3 % mod +13 % ved 14 kg), konsistent med at cellens drift er relativ eller klemmen er mere stiv ved 60 kg. Ikke bevist.
- Lyd: kuglen hørtes kun ved 100 rpm-steppet (ca. 91 rpm). rms/bånd viser intet; envelope-analyse er aftalt og afventer (lokal h5 beholdt).
## Åbent
Kold nul-aflæsning (venter på Kim), quantity_applied_ml/batch_number, envelope-analyse Test 7/8/run 1, Test 9 = H1 Power 22 ved 150 kg.
