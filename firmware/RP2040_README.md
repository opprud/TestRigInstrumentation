# RP2040 Firmware – Seeed XIAO RP2040
### ForeverBearing TestRig – Setup, Compilation, Flashing & Calibration

---

## Table of Contents

1. [Hardware](#hardware)
2. [Setup on Raspberry Pi](#setup-on-raspberry-pi)
3. [Compilation](#compilation)
4. [Uploading to the Board](#uploading-to-the-board)
5. [Serial Monitor](#serial-monitor)
6. [Command Reference](#command-reference)
7. [Load Cell Calibration](#load-cell-calibration)

---

## Hardware

| Component | Pin (RP2040) |
|-----------|-------------|
| HX711 DOUT | GPIO 4 |
| HX711 SCK | GPIO 2 |
| Tachometer | GPIO 0 |

The board connects to the Raspberry Pi via USB.

---

## Setup on Raspberry Pi

### 1. Install PlatformIO

```bash
pip3 install platformio --break-system-packages
```

### 2. Add PlatformIO to PATH

```bash
export PATH=$PATH:~/.local/bin
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

### 3. Clone the repository

```bash
git clone <repo-url>
cd TestRigInstrumentation/firmware
```

### 4. Fix `platformio.ini`

Make sure the file looks like this:

```ini
[env:seeed-xiao-rp2040]
platform = https://github.com/maxgerhardt/platform-raspberrypi.git
board = seeed_xiao_rp2040
framework = arduino
monitor_speed = 115200
```

> **Important:** `board` must be `seeed_xiao_rp2040` with an **underscore**, not a hyphen.  
> `platform` must point to Earle F. Philhower's core – not `Seeed Studio`.

---

## Compilation

```bash
cd firmware
pio run
```

The first time, PlatformIO will automatically download the correct core and libraries – this may take a few minutes.

Expected output on success:
```
RAM:   [          ]   3.6% (used 9516 bytes from 262144 bytes)
Flash: [          ]   3.6% (used 74508 bytes from 2093056 bytes)
[SUCCESS]
```

---

## Uploading to the Board

Make sure the board is connected via USB, then run:

```bash
pio run --target upload
```

PlatformIO will automatically detect the port (`/dev/ttyACM0`), reboot the board into BOOTSEL mode, and flash the firmware.

Expected output on success:
```
Verifying Flash: [==============================] 100%
  OK
The device was rebooted to start the application.
[SUCCESS]
```

---

## Serial Monitor

Open the serial monitor to communicate with the board:

```bash
pio device monitor
```

- Baud rate: `115200`
- Quit: `Ctrl+C`

Once connected, the board sends a banner:
```
OK READY vendor=ForeverBearing device=RP2040 fw=1.1.0
```

Commands are sent as plain text followed by **Enter** (LF/CRLF).

---

## Command Reference

### General

| Command | Description | Example response |
|---------|-------------|-----------------|
| `PING` | Test the connection | `OK PONG` |
| `INFO` | Show firmware info | `OK INFO vendor=ForeverBearing device=RP2040 fw=1.1.0` |

### Load Cell

| Command | Description | Example response |
|---------|-------------|-----------------|
| `LOAD?` | Read current weight | `OK LOAD mass_g=123.456 raw=61728 ts=1234567890` |
| `TARE` | Zero the tare (saved to EEPROM) | `OK TARE` |
| `SETCAL <slope> <tare>` | Set calibration and save | `OK SETCAL` |
| `CAL?` | Show current calibration | `OK CAL slope=0.008047000 tare=339992 gain=64` |
| `RESETCAL` | Reset to factory defaults | `OK RESETCAL` |

### HX711 Gain

| Command | Description | Example response |
|---------|-------------|-----------------|
| `GAIN?` | Show current gain | `OK GAIN gain=64` |
| `SETGAIN <64\|128>` | Set gain (saved to EEPROM) | `OK SETGAIN` |

> **Gain 64** = larger measurement range (recommended for >30 kg loads)  
> **Gain 128** = higher resolution (recommended for precision weighing <10 kg)  
> After changing gain, **SETCAL must be run again** with a new slope value.

### Tachometer

| Command | Description | Example response |
|---------|-------------|-----------------|
| `SPEED?` | Read current speed | `OK SPEED rpm=1500.00 period_ms=40.000 pulses=3000 ts=1234567890` |
| `PPR?` | Show pulses per revolution | `OK PPR ppr=1` |
| `SETPPR <n>` | Set pulses per revolution | `OK SETPPR` |

### Time Synchronisation

| Command | Description | Example response |
|---------|-------------|-----------------|
| `SETTIME <unix_ms>` | Sync clock with host | `OK SETTIME` |

### Error Codes

| Code | Meaning |
|------|---------|
| `ERR 10` | Unknown command |
| `ERR 11` | Line too long |
| `ERR 20` | HX711 timeout |
| `ERR 30` | Missing unix_ms argument |
| `ERR 31` | Missing slope/tare argument |
| `ERR 32` | Missing PPR argument |
| `ERR 33` | Invalid PPR (must not be 0) |
| `ERR 34` | Missing gain argument |
| `ERR 35` | Invalid gain (use 64 or 128) |

---

## Load Cell Calibration

Calibration requires a **known reference weight**. A 10 kg reference is strongly recommended as it is easier to place stably on the load cell than lighter weights, giving more consistent raw readings.

> **Note:** The load cell exhibits some mechanical noise (~150 g spread between consecutive readings). This is normal and related to the physical mounting of the load cell. Always use an average of multiple readings when calculating the slope.

### Current Calibration Values

These are the validated calibration values for this testrig:

| Parameter | Value |
|-----------|-------|
| slope | 0.008047 |
| tare | 339992 |
| gain | 64 |

To restore these values at any time:
```
SETCAL 0.008047 339992
```

---

### Full Calibration Procedure (from scratch)

#### Step 1 – Reset to factory defaults

```
RESETCAL
```

#### Step 2 – Tare with no load

Make sure the load cell is **completely unloaded**, then:

```
TARE
```

Confirm the tare was saved:
```
CAL?
```

Note the `tare` value from the response.

#### Step 3 – Apply reference weight and collect raw readings

Place your **10 kg reference weight** stably and centered on the load cell. Take **5 or more readings**:

```
LOAD?
LOAD?
LOAD?
LOAD?
LOAD?
```

Calculate the **average of the raw values**.

#### Step 4 – Calculate slope

```
slope = reference_weight_in_grams / (average_raw - tare)
```

Example:
```
slope = 10000 / (1485860 - 339992) = 10000 / 1145868 = 0.008727
```

#### Step 5 – Save calibration

```
SETCAL <slope> <tare>
```

Example:
```
SETCAL 0.008727 339992
```

#### Step 6 – Verify

With the 10 kg reference weight still on, take several readings:
```
LOAD?
LOAD?
LOAD?
```

If the readings are consistently close to 10000 g, calibration is complete. If not, repeat from Step 3 using the new readings to refine the slope:

```
slope_new = slope_old × (10000 / measured_average)
```

---

## EEPROM Persistence

The following settings are automatically saved to EEPROM (flash emulation) and survive a reboot:

- `slope` (calibration factor)
- `tare` (zero offset)
- `gain` (HX711 gain)

The calibration is valid as long as the `CAL2` magic number and CRC32 checksum match. On corruption or first boot, factory defaults are used:

| Parameter | Factory default |
|-----------|----------------|
| slope | 0.004000 |
| tare | 0 |
| gain | 64 |

---

## Tips for Stable Measurements

- Always place the reference weight **centered** on the load cell
- Ensure the load cell is **rigidly mounted** at both ends to avoid side loading
- Avoid vibrations in the environment during calibration
- Take **multiple readings and average** the raw values rather than relying on a single reading
- Calibrate at the **load level you will actually be measuring** – the 10 kg reference is best if measuring loads in that range

---

*Firmware v1.1.0 – ForeverBearing TestRig*
