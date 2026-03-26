# RP2040 Firmware – Seeed XIAO RP2040
### ForeverBearing TestRig – Setup, Kompilering, Upload & Kalibrering

---

## Indhold

1. [Hardware](#hardware)
2. [Opsætning på Raspberry Pi](#opsætning-på-raspberry-pi)
3. [Kompilering](#kompilering)
4. [Upload til board](#upload-til-board)
5. [Serial Monitor](#serial-monitor)
6. [Kommandoreference](#kommandoreference)
7. [Kalibrering af load cell](#kalibrering-af-load-cell)

---

## Hardware

| Komponent | Pin (RP2040) |
|-----------|-------------|
| HX711 DOUT | GPIO 4 |
| HX711 SCK | GPIO 2 |
| Tachometer | GPIO 0 |

Boardet forbindes til Raspberry Pi via USB.

---

## Opsætning på Raspberry Pi

### 1. Installer PlatformIO

```bash
pip3 install platformio --break-system-packages
```

### 2. Tilføj PlatformIO til PATH

```bash
export PATH=$PATH:~/.local/bin
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

### 3. Hent projektet

```bash
git clone <repo-url>
cd TestRigInstrumentation/firmware
```

### 4. Ret `platformio.ini`

Sørg for at filen ser sådan ud:

```ini
[env:seeed-xiao-rp2040]
platform = https://github.com/maxgerhardt/platform-raspberrypi.git
board = seeed_xiao_rp2040
framework = arduino
monitor_speed = 115200
```

> **Vigtigt:** `board` skal være `seeed_xiao_rp2040` med **underscore**, ikke bindestreg.
> `platform` skal pege på Earle F. Philhower's kerne – ikke `Seeed Studio`.

---

## Kompilering

```bash
cd firmware
pio run
```

Første gang henter PlatformIO automatisk den rigtige kerne og biblioteker – det tager et par minutter.

Forventet output ved succes:
```
RAM:   [          ]   3.6% (used 9516 bytes from 262144 bytes)
Flash: [          ]   3.6% (used 74508 bytes from 2093056 bytes)
[SUCCESS]
```

---

## Upload til board

Sørg for at boardet er forbundet via USB, og kør:

```bash
pio run --target upload
```

PlatformIO finder automatisk porten (`/dev/ttyACM0`), genstarter boardet i BOOTSEL-mode og flasher firmware.

Forventet output ved succes:
```
Verifying Flash: [==============================] 100%
  OK
The device was rebooted to start the application.
[SUCCESS]
```

---

## Serial Monitor

Åbn serial monitor til at kommunikere med boardet:

```bash
pio device monitor
```

- Baudrate: `115200`
- Afslut: `Ctrl+C`

Når forbindelsen er oprettet, sender boardet et banner:
```
OK READY vendor=ForeverBearing device=RP2040 fw=1.1.0
```

Kommandoer sendes som tekst efterfulgt af **Enter** (LF/CRLF).

---

## Kommandoreference

### Generelle kommandoer

| Kommando | Beskrivelse | Eksempel svar |
|----------|-------------|---------------|
| `PING` | Test forbindelsen | `OK PONG` |
| `INFO` | Vis firmware info | `OK INFO vendor=ForeverBearing device=RP2040 fw=1.1.0` |

### Load Cell

| Kommando | Beskrivelse | Eksempel svar |
|----------|-------------|---------------|
| `LOAD?` | Læs aktuel vægt | `OK LOAD mass_g=123.456 raw=61728 ts=1234567890` |
| `TARE` | Nulstil tare (gem i EEPROM) | `OK TARE` |
| `SETCAL <slope> <tare>` | Sæt kalibrering og gem | `OK SETCAL` |
| `CAL?` | Vis aktuel kalibrering | `OK CAL slope=0.004000000 tare=0 gain=64` |
| `RESETCAL` | Nulstil til fabriksindstillinger | `OK RESETCAL` |

### HX711 Gain

| Kommando | Beskrivelse | Eksempel svar |
|----------|-------------|---------------|
| `GAIN?` | Vis aktuel gain | `OK GAIN gain=64` |
| `SETGAIN <64\|128>` | Sæt gain (gem i EEPROM) | `OK SETGAIN` |

> **Gain 64** = større måleområde (anbefalet til >30 kg)  
> **Gain 128** = højere opløsning (anbefalet til præcisionsvejning <10 kg)  
> Efter ændring af gain **skal** SETCAL køres igen med ny slope-værdi.

### Tachometer

| Kommando | Beskrivelse | Eksempel svar |
|----------|-------------|---------------|
| `SPEED?` | Læs hastighed | `OK SPEED rpm=1500.00 period_ms=40.000 pulses=3000 ts=1234567890` |
| `PPR?` | Vis pulser per omdrejning | `OK PPR ppr=1` |
| `SETPPR <n>` | Sæt pulser per omdrejning | `OK SETPPR` |

### Tid

| Kommando | Beskrivelse | Eksempel svar |
|----------|-------------|---------------|
| `SETTIME <unix_ms>` | Synkroniser ur med host | `OK SETTIME` |

### Fejlkoder

| Kode | Betydning |
|------|-----------|
| `ERR 10` | Ukendt kommando |
| `ERR 11` | Linje for lang |
| `ERR 20` | HX711 timeout |
| `ERR 30` | Mangler unix_ms argument |
| `ERR 31` | Mangler slope/tare argument |
| `ERR 32` | Mangler PPR argument |
| `ERR 33` | Ugyldig PPR (må ikke være 0) |
| `ERR 34` | Mangler gain argument |
| `ERR 35` | Ugyldig gain (brug 64 eller 128) |

---

## Kalibrering af load cell

Kalibrering kræver en **kendt referencevægt** (f.eks. 1000 g).

### Trin 1 – Tjek gain

Vælg gain ud fra dit måleområde:

```
GAIN?
```

Skift om nødvendigt (her eksempel med gain 64 til større laster):
```
SETGAIN 64
```

### Trin 2 – Tare (nulpunktskalibrering)

Sørg for at load cellen er **aflastet** (ingen vægt på), og send:

```
TARE
```

Boardet gemmer nulpunktet i EEPROM.

### Trin 3 – Aflæs råværdi med referencevægt

Placer din **kendte referencevægt** på load cellen og aflæs raw-værdien:

```
LOAD?
```

Eksempel svar:
```
OK LOAD mass_g=1234.567 raw=312500 ts=1234567890
```

Notér `raw`-værdien (her `312500`) og din tare (fra `CAL?`):
```
CAL?
```
Eksempel: `tare=0`

### Trin 4 – Beregn slope

```
slope = referencevægt_i_gram / (raw - tare)
```

Eksempel med 1000 g referencevægt:
```
slope = 1000 / (312500 - 0) = 0.003200
```

### Trin 5 – Gem kalibrering

```
SETCAL 0.003200 0
```

Format: `SETCAL <slope> <tare_offset>`

### Trin 6 – Verificér

Placer referencevægten igen og tjek:

```
LOAD?
```

Svar bør nu vise `mass_g` tæt på din referencevægt.

### Gentag ved gain-ændring

Hvis du skifter gain med `SETGAIN` skal hele kalibreringsproceduren gentages, da gain direkte påvirker råværdierne fra HX711.

---

## EEPROM-persistence

Følgende indstillinger gemmes automatisk i EEPROM (flash-emulering) og overlever genstart:

- `slope` (kalibreringsfaktor)
- `tare` (nulpunkt)
- `gain` (HX711 gain)

Kalibreringen er gyldig så længe `CAL2`-magic og CRC32-checksum matcher. Ved korruption eller første opstart bruges fabriksindstillingerne:

| Parameter | Fabriksværdi |
|-----------|-------------|
| slope | 0.004000 |
| tare | 0 |
| gain | 64 |

---

*Firmware v1.1.0 – ForeverBearing TestRig*
