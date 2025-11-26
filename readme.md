# MSO-X Data Acquisition & Telemetry

Tools to acquire high-fidelity waveforms from a **Keysight/Agilent MSO-X 2024A** using SCPI/TCPIP, store them in **HDF5**, and optionally attach **telemetry** (loadcell, RPM, temperature).  
Now includes full **auto-detection** of the oscilloscope via `scope_utils.py`, with **preferred_port** override and **scope_cache.json** persistence.

---

## 🚀 Features

### 🟡 1) Oscilloscope acquisition (SCPI/TCPIP)
- Auto-detection of MSO-X scope:
  - Uses **scope_cache.json** if cached
  - Tries **preferred_port** from config  
  - Tries hostnames: `msox-2024a`, `scope.local`, …
  - Falls back to network scan & VISA
- Robust IEEE-488.2 block reads
- Supports:
  - `WORD` (16-bit) or `BYTE` waveform transfer
  - `NORM`, `HRES`, `AVER` acquisition types
  - `AUTO` or `NORM` trigger sweep
- Fresh capture per sweep:  
  `:DIGitize → *OPC? → :WAV:PRE? → :WAV:DATA?`
- Timezone-aware timestamps (CET/CEST using tzdata) + UTC

---

## 📦 2) Storage (HDF5)
Data is stored in a metadata-rich layout:

```
/metadata
/sweeps/sweep_000/<alias>/time
/sweeps/sweep_000/<alias>/voltage
```

Each channel includes:
- x_increment, y_increment
- reference offsets
- sample rate
- points reported

---

## 📊 3) Telemetry (optional)
Supports:
- **RP2040 (Arduino)**:
  - Load cell via HX711
  - RPM tachometer
  - Configurable EEPROM calibration
  - ASCII command interface (`LOAD?`, `SPEED?`, `CAL?`, …)
- **Omron E5CC** temperature via RS-485/Modbus

Telemetry is attached to each sweep in HDF5.

---

## 📈 4) Plotting
`plot_waveform.py` enables:
- Time series plot
- FFT
- Spectrogram
- Scope-style channel coloring

---

## 📁 Repository layout

```
acquire_scope_data.py      # SCPI → HDF5 acquisition (uses scope_utils.py)
scope_utils.py             # Auto-detect, cache, socket/VISA abstraction
plot_waveform.py
rp2040_tool.py
e5cc_reader.py
firmware/
  rp2040_hx711_tacho/
      rp2040_hx711_tacho.ino
config.json
requirements.txt
scope_cache.json           # Auto-generated: stores last known scope host + port
README.md
```

---

# ⚙️ Installation

## 1) Install Python
Requires **Python 3.11+** (recommended on Windows).

```bash
python --version
```

## 2) Install dependencies

Windows:
```bash
py -3.11 -m pip install numpy h5py pyvisa tzdata
```

Linux/macOS:
```bash
python3 -m pip install -r requirements.txt
```

---

# 📝 Config (config.json)

Below is a minimal working configuration using autodetect:

```json
{
  "scope": {
    "preferred_port": 5025
  },

  "acquisition": {
    "points": 2000,
    "samples": 1,
    "interval_sec": 1.0,
    "waveform_format": "WORD",
    "points_mode": "NORM",
    "trigger_sweep": "AUTO",
    "acq_type": "NORM"
  },

  "channels": [
    { "name": "CH1", "source": "CHAN1", "enabled": true }
  ],

  "store": {
    "output_file": "data.h5",
    "timestamped": false,
    "compress": "none",
    "chunk": false
  }
}
```

## Notes:
- `"preferred_port"` overrides the default port list.
- `scope_cache.json` stores `{host, port}` from last successful detection.
- If cached scope is online → immediate connect (< 50 ms).
- If not → autodetect fallback methods will be used.

---

# ▶️ Running acquisition

```bash
python acquire_scope_data.py config.json
```

Optional debug mode:

```bash
python acquire_scope_data.py config.json --debug
```

Debug mode prints:
- Autodetect steps  
- Cache hits  
- Network scan attempts  
- VISA resources  
- SCPI error traces  

---

# 🔧 How autodetect works (scope_utils.py)

Priority:

1. **scope_cache.json**  
2. **preferred_port** + known hosts  
3. VISA discovery  
4. Subnet scan (`192.168.0.x`, `192.168.1.x`, `10.0.0.x`)

The first successful connection is cached.

---

# 🛠️ Troubleshooting

### "TimeoutError: timed out"
Likely due to missing waveform data.

Check:
- CH1/CH2 is ON  
- Scope in STOP  
- Trigger Sweep = AUTO  
- DIGITIZE produces waveform  

### "tzdata not found"
Install:

```bash
python -m pip install tzdata
```

### "No module named numpy"
Install:

```bash
python -m pip install numpy
```

---

# 🎉 Summary

This repository now supports:

- Fully automatic scope discovery  
- Configurable port override  
- Cached scope settings  
- Fast reconnection  
- Clean separation of acquisition, telemetry, plotting  
- Stable waveform transfer with IEEE-488.2 parsing  
- Windows and Linux compatibility  
