# ForeverBearing — Test Rig Instrumentation

System til styring og dataopsamling for lejeudholdenhedstests. Kombinerer oscilloskop-opsamling (HDF5), motorregulering (VFD), temperaturstyring (Omron E5CC), lastsensor og tachometer (RP2040) samt effektstyring (Shelly Pro 4PM).

---

## Indholdsfortegnelse

- [Systemarkitektur](#systemarkitektur)
- [Hardware](#hardware)
- [Hurtig start](#hurtig-start)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Kørsel af test](#kørsel-af-test)
- [Shelly effektstyring](#shelly-effektstyring)
- [Filstruktur](#filstruktur)
- [HDF5 dataformat](#hdf5-dataformat)

---

## Systemarkitektur

```
Raspberry Pi
├── py/
│   ├── api_server.py          ← FastAPI backend (port 8000)
│   ├── acquire_scope_data.py  ← Osciloskop + HDF5 opsamling
│   ├── test_runner.py         ← Testsekvens styring (RPM/temp PI-regulering)
│   ├── config.json            ← Scope og hardware konfiguration
│   └── shelly_config.json     ← Shelly MQTT konfiguration
└── react/
    └── src/                   ← React dashboard (port 3000)
```

**Dataflow under en test:**
```
acquire_scope_data.py  →  HDF5 fil (scope sweeps + telemetri)
test_runner.py         →  JSONL fil (RPM/temp samples)
api_server.py          →  REST API → React Dashboard (live telemetri)
```

---

## Hardware

| Enhed | Interface | Funktion |
|---|---|---|
| Keysight MSO-X 2024A | TCP/IP (port 5025) | Oscilloskop — AE + UL kanaler |
| RS PRO RS510 VFD | RS485/Modbus (slave 3) | Motorstyring |
| Omron E5CC | RS485/Modbus (slave 2) | Temperaturstyring |
| Seeed XIAO RP2040 | USB Serial | Lastsensor + Tachometer |
| Shelly Pro 4PM | MQTT | Effektstyring (4 kanaler) |

---

## Hurtig start

### 1. Klon og start systemet

```bash
git clone <repo>
cd ForeverBearing/sw/TestRigInstrumentation
bash start_system.sh
```

Åbn browser:
- **Dashboard:** http://localhost:3000
- **Effektstyring:** http://localhost:3000/shelly
- **API docs:** http://localhost:8000/docs

### 2. Vælg testprofil i UI

1. Gå til http://localhost:3000
2. Vælg profil i "Configuration File" (fx *First-Oil Validation*)
3. Tryk **Start**
4. Følg live telemetri: RPM, temperatur, last
5. Tryk **Stop** for at afslutte før tid — HDF5 filen gemmes automatisk

### 3. Kør test fra kommandolinje

```bash
cd py
source .venv/bin/activate

# Med testprofil (automatisk RPM + temp)
python3 acquire_scope_data.py config.json ../react/public/config/first-oil.json

# Manuel mode (sæt RPM/temp selv på VFD/Omron)
python3 acquire_scope_data.py config.json
```

---

## Installation

### Krav

- Python 3.10+
- Node.js 18+
- `mosquitto` klient (valgfrit, til debug)

### Automatisk installation

`start_system.sh` håndterer alt automatisk:

```bash
bash start_system.sh
```

Scriptet:
1. Opretter Python virtual environment (`py/.venv`)
2. Installerer Python afhængigheder fra `requirements.txt`
3. Starter API server (port 8000)
4. Installerer Node.js afhængigheder (første gang)
5. Starter React dev server (port 3000)

### Manuel installation

```bash
# Python
cd py
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# React
cd ../react
npm install
npm run dev
```

### Python afhængigheder (`requirements.txt`)

```
numpy, h5py, pyserial, pyvisa-py, pymodbus, fastapi, uvicorn, paho-mqtt
```

---

## Konfiguration

### `py/config.json`

Hoved-konfiguration for scope, kanaler og test:

```json
{
  "scope_ip": "169.254.172.2",        ← Scope IP-adresse
  "channels": [
    {"name": "AE",  "source": "CHAN1", "enabled": true},
    {"name": "UL",  "source": "CHAN2", "enabled": true}
  ],
  "store": {
    "output_file": "data/test.h5"     ← Output mappe
  },
  "bearing": { ... },                  ← Lejeparametre (gemmes i HDF5)
  "lubricant": { ... }                 ← Smøremiddeldata (gemmes i HDF5)
}
```

### Testprofiler (`react/public/config/`)

| Fil | Beskrivelse | Varighed |
|---|---|---|
| `first-oil.json` | Første olie test — RPM 500→3000 rpm | 170 min |
| `test-profile.json` | Standard test — RPM 1000→2000 rpm | 15 min |
| `endurance-profile.json` | Udholdenhedstest — 1800→2200 rpm | 61 min |
| `high-stress-profile.json` | Høj belastning — op til 3200 rpm | 14 min |
| `lub1_validation.json` | Smøremiddel validering | 110 min |

**Profil struktur:**

```json
{
  "name": "Min Test",
  "duration_minutes": 15,
  "setpoints": {
    "rpm": [
      {"time_sec": 0,   "value": 1000},
      {"time_sec": 600, "value": 2000}
    ],
    "temperature": [
      {"time_sec": 0,   "value": 40},
      {"time_sec": 300, "value": 60}
    ]
  },
  "acquisition": {
    "scope_points": 250000,
    "interval_sec": 3,
    "samples_per_step": 3
  },
  "scope_channels": {
    "AE": {"timebase_range": 0.02, "volt_range": 1.0, "coupling": "DC"},
    "UL": {"timebase_range": 0.02, "volt_range": 0.8, "coupling": "DC"}
  }
}
```

> **Vigtigt:** `duration_minutes` skal dække det maksimale `time_sec` i setpoints.
> Gyldige `volt_range` værdier for MSO-X: 0.016, 0.04, 0.08, 0.2, 0.4, 0.8, 1.0, 2.0, 4.0, 8.0 (V)

### `py/shelly_config.json`

```json
{
  "mqtt": {
    "host": "185.81.165.190",
    "port": 1883,
    "username": "mqttuser",
    "password": "3711"
  },
  "device_id": "shellypro4pm-c8f09e84cdf8",
  "channels": [
    {"id": 0, "name": "Heater",    "description": "Oil heater"},
    {"id": 1, "name": "Channel 2", "description": "Spare"},
    {"id": 2, "name": "Channel 3", "description": "Spare"},
    {"id": 3, "name": "CPU",       "description": "Raspberry Pi"}
  ]
}
```

---

## Kørsel af test

### Fra UI

1. Åbn http://localhost:3000
2. Vælg profil → **Start**
3. Live telemetri opdateres hvert sekund
4. HDF5 filen vises i "HDF5 Data Log" med filstørrelse og sweep-tæller
5. **Stop** gemmer filen og stopper motor + scope

### Fra kommandolinje

```bash
cd py && source .venv/bin/activate

# Med profil (automatisk)
python3 acquire_scope_data.py config.json ../react/public/config/test-profile.json

# Med debug output
python3 acquire_scope_data.py config.json ../react/public/config/test-profile.json --debug

# Manuel (ingen profil)
python3 acquire_scope_data.py config.json
```

### Output

Filer gemmes i `data/runs/<timestamp>/`:

```
data/runs/20260319_142500/
├── scope_20260319_142500.h5           ← HDF5 scope data + metadata
└── telemetry_20260319_142500_*.jsonl  ← Telemetri log
```

---

## Shelly effektstyring

### Web UI

Åbn http://localhost:3000/shelly

- Toggle knapper til on/off per kanal
- Live effekt (W), strøm (mA), spænding (V)
- Total aktiv effekt øverst

### Fra kommandolinje (anden PC)

```bash
pip install paho-mqtt
python3 shelly_control.py --status

python3 shelly_control.py --on cpu        # Tænd CPU (kanal 3)
python3 shelly_control.py --off heater    # Sluk Heater (kanal 0)
python3 shelly_control.py --on 2          # Tænd kanal 2
```

> Bruges til at genstarte Raspberry Pi'en hvis CPU kanalen er slukket.

---

## HDF5 dataformat

Åbn filer med [myHDF5](https://myhdf5.hdfgroup.org) eller Python:

```python
import h5py
with h5py.File("scope_20260319.h5", "r") as f:
    # Metadata
    bearing = dict(f["metadata/bearing"].attrs)
    scope   = dict(f["metadata/scope_settings/AE"].attrs)

    # Sweep data
    voltage = f["sweeps/sweep_000/AE/voltage"][:]
    time    = f["sweeps/sweep_000/AE/time"][:]

    # Telemetri per sweep
    rpm  = f["sweeps/sweep_000"].attrs["telem_rpm_meas"]
    temp = f["sweeps/sweep_000"].attrs["telem_omron_pv_c"]
```

**Struktur:**

```
scope_*.h5
├── metadata/
│   ├── bearing/          ← Lejeparametre (fra config.json)
│   ├── lubricant/        ← Smøremiddeldata (fra config.json)
│   ├── scope_settings/
│   │   ├── AE/           ← Kanal indstillinger (range, coupling osv.)
│   │   └── UL/
│   └── test_parameters/  ← Testparametre
└── sweeps/
    ├── sweep_000/
    │   ├── AE/
    │   │   ├── time      ← Tidsvektor (s)
    │   │   └── voltage   ← Spændingsdata (V)
    │   └── UL/
    │       ├── time
    │       └── voltage
    │   attrs:
    │       telem_rpm_meas      ← Målt RPM ved sweep
    │       telem_omron_pv_c    ← Temperatur (°C)
    │       telem_mass_g        ← Last (g)
    │       telem_vfd_cmd_hz    ← VFD frekvens (Hz)
    ├── sweep_001/
    └── ...
```

---

## API endpoints

| Endpoint | Beskrivelse |
|---|---|
| `GET /api/run/status` | Kørselsstatus (elapsed, steps, telemetri) |
| `POST /api/run/start` | Start test med profil |
| `POST /api/run/stop` | Stop kørende test |
| `GET /api/telemetry` | Live telemetri (RPM, temp, last) |
| `GET /api/hdf5/status` | HDF5 filstatus (størrelse, sweeps, diskplads) |
| `GET /api/shelly/status` | Shelly kanal status |
| `POST /api/shelly/switch/{id}` | Tænd/sluk Shelly kanal |
| `GET /api/scope/waveform` | Live waveform preview |
| `GET /docs` | Interaktiv API dokumentation |