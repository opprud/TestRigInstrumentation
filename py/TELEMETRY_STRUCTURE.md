# Telemetry Data Structure - Per-Sweep Collection

## How It Works

The acquisition system collects **fresh telemetry readings for EACH sweep**, not just once at the beginning. This ensures you capture changing conditions throughout the test.

## HDF5 Structure with Telemetry

```
/metadata (root-level, captured ONCE at start)
  ├─ project: "ForeverBearing"
  ├─ operator: "morten"
  ├─ telemetry_enabled: true
  ├─ test_parameters: {"target_rpm": 1500, ...}  ← TARGETS
  └─ ...

/sweeps/
  ├─ sweep_000 (captured at time T₀)
  │   ├─ timestamp_local: "2025-10-27T09:19:47+01:00"
  │   ├─ timestamp_utc: "2025-10-27T08:19:47+00:00"
  │   ├─ telemetry_timestamp_utc: "2025-10-27T08:19:47.1+00:00"  ← Fresh reading
  │   ├─ telemetry_rpm: 1487.3              ← ACTUAL RPM at T₀
  │   ├─ telemetry_temperature_c: 58.2      ← ACTUAL temp at T₀
  │   ├─ telemetry_mass_g: 203.5            ← ACTUAL load at T₀
  │   ├─ telemetry_period_ms: 40.43
  │   ├─ telemetry_pulses: 14873
  │   └─ [AE, Accel, UL, Temp channel groups...]
  │
  ├─ sweep_001 (captured at time T₁ = T₀ + interval)
  │   ├─ timestamp_local: "2025-10-27T09:19:50+01:00"
  │   ├─ timestamp_utc: "2025-10-27T08:19:50+00:00"
  │   ├─ telemetry_timestamp_utc: "2025-10-27T08:19:50.1+00:00"  ← Fresh reading
  │   ├─ telemetry_rpm: 1502.1              ← ACTUAL RPM at T₁ (different!)
  │   ├─ telemetry_temperature_c: 59.7      ← ACTUAL temp at T₁ (rising)
  │   ├─ telemetry_mass_g: 204.1            ← ACTUAL load at T₁
  │   └─ [channel groups...]
  │
  └─ sweep_002 (captured at time T₂ = T₁ + interval)
      ├─ timestamp_local: "2025-10-27T09:19:53+01:00"
      ├─ telemetry_rpm: 1515.8              ← ACTUAL RPM at T₂ (changed again!)
      ├─ telemetry_temperature_c: 61.3      ← ACTUAL temp at T₂ (still rising)
      ├─ telemetry_mass_g: 203.8            ← ACTUAL load at T₂
      └─ [channel groups...]
```

## Key Points

### ✅ Per-Sweep Collection (Current Implementation)

**Timeline:**
```
Time: T₀           T₀+3s         T₀+6s
      │            │             │
      ├─ Sweep 0 ──┤             │
      │  RPM: 1487 │             │
      │  Temp: 58°C│             │
      │            │             │
      │            ├─ Sweep 1 ───┤
      │            │  RPM: 1502  │
      │            │  Temp: 60°C │
      │            │             │
      │            │             ├─ Sweep 2
      │            │             │  RPM: 1516
      │            │             │  Temp: 61°C
```

**Code Location:**
In `acquire_scope_data.py:266-298`, the telemetry collection happens **inside** the sweep loop:

```python
for i in range(samples):              # Line 266 - SWEEP LOOP
    ts_local, ts_utc = now_pair()
    sweep_grp = sweeps_grp.create_group(f"sweep_{i:03d}")

    # ... set sweep attributes ...

    # Collect telemetry FOR THIS SPECIFIC SWEEP
    if collect_telemetry:             # Line 285
        telemetry_data = collect_all_telemetry(
            rp2040_port=rp2040_port,
            modbus_config=modbus_config,
            include_timestamp=True
        )
        # Store as attributes on THIS sweep
        for key, value in telemetry_data.items():
            sweep_grp.attrs[f"telemetry_{key}"] = value

    # ... acquire scope data ...
```

### ❌ Wrong Approach (NOT how we do it)

Some systems only collect telemetry once:
```python
# WRONG - Don't do this!
telemetry_data = collect_all_telemetry()  # Only once before loop

for i in range(samples):
    sweep_grp = ...
    # Using same telemetry_data for all sweeps - BAD!
    sweep_grp.attrs["rpm"] = telemetry_data["rpm"]
```

This would give the same RPM/temp for all sweeps, which doesn't reflect reality.

## Usage Examples

### Example 1: Track Changing Conditions

```python
import h5py
import matplotlib.pyplot as plt

# Load HDF5 file
h5file = 'data/test_20251027_143022.h5'

times = []
rpms = []
temps = []
loads = []

with h5py.File(h5file, 'r') as f:
    for sweep_name in sorted(f['/sweeps'].keys()):
        sweep = f[f'/sweeps/{sweep_name}']

        # Get timestamp
        ts = sweep.attrs.get('timestamp_utc')
        times.append(ts)

        # Get telemetry readings
        rpms.append(sweep.attrs.get('telemetry_rpm', None))
        temps.append(sweep.attrs.get('telemetry_temperature_c', None))
        loads.append(sweep.attrs.get('telemetry_mass_g', None))

# Plot conditions over time
fig, axes = plt.subplots(3, 1, figsize=(10, 8))

axes[0].plot(range(len(rpms)), rpms, 'o-')
axes[0].set_ylabel('RPM')
axes[0].set_title('Conditions During Test')
axes[0].grid(True)

axes[1].plot(range(len(temps)), temps, 'o-', color='orange')
axes[1].set_ylabel('Temperature (°C)')
axes[1].grid(True)

axes[2].plot(range(len(loads)), loads, 'o-', color='green')
axes[2].set_ylabel('Load (g)')
axes[2].set_xlabel('Sweep Number')
axes[2].grid(True)

plt.tight_layout()
plt.show()
```

### Example 2: Compare Target vs Actual

```python
import h5py
import json

h5file = 'data/test_20251027_143022.h5'

with h5py.File(h5file, 'r') as f:
    # Get target from test parameters (ONCE at start)
    test_params = json.loads(f['/metadata'].attrs['test_parameters'])
    target_rpm = test_params['target_rpm']
    target_temp = test_params['target_temperature_c']

    print(f"Target RPM: {target_rpm}")
    print(f"Target Temperature: {target_temp}°C")
    print()

    # Get actual readings per sweep
    print("Actual Readings Per Sweep:")
    print("Sweep | RPM      | Temp    | Error")
    print("------|----------|---------|-------")

    for sweep_name in sorted(f['/sweeps'].keys()):
        sweep = f[f'/sweeps/{sweep_name}']

        actual_rpm = sweep.attrs.get('telemetry_rpm', 0)
        actual_temp = sweep.attrs.get('telemetry_temperature_c', 0)

        rpm_error = abs(actual_rpm - target_rpm)

        print(f"{sweep_name} | {actual_rpm:6.1f}  | {actual_temp:5.1f}°C | {rpm_error:5.1f}")
```

### Example 3: Correlate Vibration with Speed

```python
import h5py
import numpy as np

h5file = 'data/test_20251027_143022.h5'

results = []

with h5py.File(h5file, 'r') as f:
    for sweep_name in sorted(f['/sweeps'].keys()):
        sweep = f[f'/sweeps/{sweep_name}']

        # Get actual RPM for this sweep
        rpm = sweep.attrs.get('telemetry_rpm', None)

        if rpm is not None:
            # Get vibration signal
            accel_data = sweep['Accel/voltage'][:]
            rms_vibration = np.sqrt(np.mean(accel_data**2))

            results.append({
                'rpm': rpm,
                'vibration_rms': rms_vibration
            })

# Analyze correlation
import pandas as pd
df = pd.DataFrame(results)
print(f"Vibration vs RPM correlation: {df['rpm'].corr(df['vibration_rms']):.3f}")
```

## Configuration

### Enable Telemetry in config.json

```json
{
  "telemetry": {
    "enabled": true,
    "rp2040_port": "/dev/tty.usbmodem14201",
    "modbus_config": "modbus_config.json"
  },

  "test_parameters": {
    "test_name": "Endurance test",
    "target_rpm": 1500,
    "target_temperature_c": 60,
    "expected_load_g": 200,
    "duration_minutes": 60
  }
}
```

### Test Telemetry Collection

```bash
# Test RP2040 (load + speed)
python3 telemetry_collector.py --rp2040-port /dev/tty.usbmodem14201 --json

# Test full system (RP2040 + Modbus temp)
python3 telemetry_collector.py \
  --rp2040-port /dev/tty.usbmodem14201 \
  --modbus-config modbus_config.json \
  --json
```

Expected output:
```json
{
  "timestamp_utc": "2025-10-27T08:19:47.123456+00:00",
  "mass_g": 205.3,
  "rpm": 1523.4,
  "period_ms": 39.4,
  "pulses": 15234,
  "temperature_c": 61.2
}
```

## Timing Considerations

### Telemetry Collection Timing

The telemetry is collected **immediately before** each scope acquisition:

```
Sweep N timeline:
│
├─ Record timestamp (timestamp_local, timestamp_utc)
├─ Collect telemetry (RPM, temp, load) ← ~100-500ms
│    └─ Store as sweep_N attributes
├─ Acquire scope data (all channels)   ← ~1-2s depending on points
│    └─ Store as sweep_N/channel datasets
└─ Sleep interval_sec before next sweep
```

**Timing accuracy:**
- Telemetry and scope timestamps differ by <1 second
- Both are representative of conditions during that sweep
- For slowly changing conditions (temperature), this is excellent
- For fast transients, you may want to reduce `interval_sec`

### Adjusting Collection Rate

In `config.json`:
```json
{
  "acquisition": {
    "samples": 10,        ← Number of sweeps
    "interval_sec": 3     ← Time between sweeps
  }
}
```

**Guidelines:**
- **Fast changing (RPM ramp)**: Use `interval_sec: 1-2`
- **Steady state**: Use `interval_sec: 5-10`
- **Long endurance**: Use `interval_sec: 60` (1 per minute)

## Verifying Per-Sweep Collection

Run the verification tool:
```bash
python3 verify_telemetry_per_sweep.py data/your_file.h5
```

This shows each sweep's telemetry to confirm they're different.

## Summary

✅ **Telemetry is collected PER SWEEP** - already implemented correctly
✅ **Each sweep has independent readings** - tracks changing conditions
✅ **Target vs Actual comparison** - test_parameters (target) vs telemetry (actual)
✅ **Timestamped** - Both sweep timestamp and telemetry timestamp recorded
✅ **Non-blocking** - Missing sensors don't stop acquisition

The system is ready to track changing speed, temperature, and load throughout your experiments!
