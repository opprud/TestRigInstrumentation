#!/usr/bin/env python3
"""
Load sampled JSON data from OE Bearing Brain devices, scale to SI/useful units,
and plot using Plotly. Optionally compute FFT for frequency-domain analysis.

Usage:
    python plot_samples.py samples/OE*.json                              # time-domain plot
    python plot_samples.py samples/OE*.json --raw                        # plot without scaling
    python plot_samples.py samples/OE*.json --sensors 3 4                # only specific sensors
    python plot_samples.py samples/OE*.json --fft -c pdm_mic_config.json # FFT with sample rates from config
    python plot_samples.py samples/OE*.json --fft --fft-db               # FFT in dB scale
    python plot_samples.py samples/OE*.json --export csv                 # export scaled data
"""

import argparse
import json
import math
import os
import sys
import glob
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Sensor metadata: name, unit after scaling, and default scale/offset
# When scale/offset come from device config, these defaults are fallbacks.
# ---------------------------------------------------------------------------

SENSOR_META = {
    0:  {"name": "Battery Level",          "unit": "%",   "group": "Battery"},
    1:  {"name": "Ambient Temperature",    "unit": "°C",  "group": "Temperature"},
    2:  {"name": "Machine Temperature",    "unit": "°C",  "group": "Temperature"},
    3:  {"name": "Ambient Microphone",     "unit": "Pa",  "group": "Microphone"},
    4:  {"name": "Machine Microphone",     "unit": "Pa",  "group": "Microphone"},
    5:  {"name": "Acceleration ADXL1002",  "unit": "g",   "group": "ADXL1002"},
    6:  {"name": "Acceleration ADXL362 X", "unit": "g",   "group": "ADXL362"},
    7:  {"name": "Acceleration ADXL362 Y", "unit": "g",   "group": "ADXL362"},
    8:  {"name": "Acceleration ADXL362 Z", "unit": "g",   "group": "ADXL362"},
    9:  {"name": "Acceleration ISM330 X",  "unit": "raw", "group": "ISM330 Acc"},
    10: {"name": "Acceleration ISM330 Y",  "unit": "raw", "group": "ISM330 Acc"},
    11: {"name": "Acceleration ISM330 Z",  "unit": "raw", "group": "ISM330 Acc"},
    12: {"name": "Gyroscope ISM330 X",     "unit": "raw", "group": "ISM330 Gyro"},
    13: {"name": "Gyroscope ISM330 Y",     "unit": "raw", "group": "ISM330 Gyro"},
    14: {"name": "Gyroscope ISM330 Z",     "unit": "raw", "group": "ISM330 Gyro"},
    15: {"name": "Magnetic MMC5603NJ X",   "unit": "µT",  "group": "MMC5603"},
    16: {"name": "Magnetic MMC5603NJ Y",   "unit": "µT",  "group": "MMC5603"},
    17: {"name": "Magnetic MMC5603NJ Z",   "unit": "µT",  "group": "MMC5603"},
    18: {"name": "Magnetic DRV425",        "unit": "raw", "group": "DRV425"},
}

# Default scale factors from protocol docs (used as fallback when no device config)
DEFAULT_SCALE_FACTORS = {
    1:  {"scale": 0.0078125, "offset": 0},       # Temperature: °C/LSB
    2:  {"scale": 0.0078125, "offset": 0},        # Temperature: °C/LSB
    3:  {"scale": 0.000305,  "offset": 0},        # Microphone: Pa/LSB
    4:  {"scale": 0.000305,  "offset": 0},        # Microphone: Pa/LSB
    5:  {"scale": 0.0001097, "offset": -2522920}, # ADXL1002: g/LSB
    6:  {"scale": 0.02,      "offset": 0},        # ADXL362 X: g/LSB (4G range)
    7:  {"scale": 0.02,      "offset": 0},        # ADXL362 Y: g/LSB
    8:  {"scale": 0.02,      "offset": 0},        # ADXL362 Z: g/LSB
    15: {"scale": 0.09765625, "offset": 0},       # MMC5603: µT/LSB
    16: {"scale": 0.09765625, "offset": 0},       # MMC5603: µT/LSB
    17: {"scale": 0.09765625, "offset": 0},       # MMC5603: µT/LSB
}

# Config group/sub_group mappings for retrieving scale/offset from device configs
# Format: sensor_id -> {"scale": (main_group, sub_group), "offset": (main_group, sub_group)}
CONFIG_LOOKUP = {
    1:  {"scale": (21, 1)},
    2:  {"scale": (21, 1)},
    3:  {"scale": (32, 3)},
    4:  {"scale": (32, 3)},
    5:  {"scale": (71, 0), "offset": (71, 1)},
    6:  {"scale": (48, 2), "offset": (48, 5)},
    7:  {"scale": (48, 3), "offset": (48, 6)},
    8:  {"scale": (48, 4), "offset": (48, 7)},
    15: {"scale": (64, 0)},
    16: {"scale": (64, 0)},
    17: {"scale": (64, 0)},
}

BATTERY_CAPACITY_MAH = 2600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_config_value(configs: list, main_group: int, sub_group: int):
    """Look up a config value by main_group and sub_group."""
    for entry in configs:
        if entry["main_group"] == main_group and entry["sub_group"] == sub_group:
            return entry["config_value"]
    return None


def get_scale_and_offset(sensor_id: int, device_configs: list | None) -> tuple[float, float]:
    """
    Get scale factor and offset for a sensor.
    Priority: device configs > protocol defaults > identity (1, 0).
    """
    scale = 1.0
    offset = 0.0

    # Try device configs first
    if device_configs and sensor_id in CONFIG_LOOKUP:
        lookup = CONFIG_LOOKUP[sensor_id]
        if "scale" in lookup:
            val = get_config_value(device_configs, *lookup["scale"])
            if val is not None:
                scale = val
        if "offset" in lookup:
            val = get_config_value(device_configs, *lookup["offset"])
            if val is not None:
                offset = val
        return scale, offset

    # Fall back to protocol defaults
    if sensor_id in DEFAULT_SCALE_FACTORS:
        d = DEFAULT_SCALE_FACTORS[sensor_id]
        return d["scale"], d["offset"]

    return scale, offset


def scale_sensor_data(sensor_id: int, raw_data: list, device_configs: list | None) -> list:
    """Scale raw sensor data to SI units."""
    if sensor_id == 0:
        # Battery: convert mAh usage to percentage
        return [((BATTERY_CAPACITY_MAH - v) / BATTERY_CAPACITY_MAH) * 100 for v in raw_data]

    scale, offset = get_scale_and_offset(sensor_id, device_configs)
    return [(v - offset) * scale for v in raw_data]


def load_sample_file(filepath: str) -> dict:
    """Load a sample JSON file."""
    with open(filepath) as f:
        return json.load(f)


def get_sensor_info(sensor_id: int) -> dict:
    """Get sensor metadata."""
    return SENSOR_META.get(sensor_id, {
        "name": f"Unknown Sensor {sensor_id}",
        "unit": "raw",
        "group": "Unknown",
    })


def get_sampling_rate(sensor_id: int, sensor_infos: list | None) -> float | None:
    """Try to get sampling rate from sensor_infos in the JSON."""
    if not sensor_infos:
        return None
    for info in sensor_infos:
        if info.get("id_for_device") == sensor_id:
            return info.get("sampling_rate")
    return None


# ---------------------------------------------------------------------------
# FFT
# ---------------------------------------------------------------------------

def compute_fft(data: list[float], sampling_rate: float, db: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute single-sided FFT magnitude spectrum.
    Returns (frequencies, magnitudes).
    If db=True, magnitudes are in dB (20*log10).
    """
    n = len(data)
    signal = np.array(data)
    # Remove DC offset
    signal = signal - np.mean(signal)
    # Apply Hanning window to reduce spectral leakage
    window = np.hanning(n)
    signal = signal * window

    fft_vals = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)

    # Single-sided magnitude, normalized by N
    magnitudes = 2.0 * np.abs(fft_vals) / n
    # DC and Nyquist don't get doubled
    magnitudes[0] /= 2.0
    if n % 2 == 0:
        magnitudes[-1] /= 2.0

    if db:
        # Convert to dB, floor at -120 dB
        magnitudes = 20 * np.log10(np.maximum(magnitudes, 1e-6))

    return freqs, magnitudes


def plot_fft(all_traces: list[dict], title: str = "FFT", db: bool = False):
    """Plot FFT of sensor traces, grouped by sensor type."""
    # Filter to traces with valid sampling rates
    valid = [t for t in all_traces if t.get("sampling_rate") and t["sampling_rate"] > 0]
    if not valid:
        print("No traces with known sampling rate — cannot compute FFT.")
        print("Provide a config file with sensor_infos using -c / --config.")
        return

    skipped = len(all_traces) - len(valid)
    if skipped:
        print(f"Skipping {skipped} trace(s) without sampling rate for FFT.")

    # Group by sensor group
    groups = {}
    for t in valid:
        g = t["group"]
        groups.setdefault(g, []).append(t)

    group_names = sorted(groups.keys())
    n_groups = len(group_names)

    fig = make_subplots(
        rows=n_groups, cols=1,
        shared_xaxes=False,
        vertical_spacing=max(0.02, 0.15 / n_groups),
        subplot_titles=[f"{g} — FFT" for g in group_names],
    )

    colors = [
        "#636EFA", "#EF553B", "#00CC96", "#AB63FA",
        "#FFA15A", "#19D3F3", "#FF6692", "#B6E880",
        "#FF97FF", "#FECB52",
    ]

    y_label = "Magnitude [dB]" if db else "Magnitude"

    for row_idx, group_name in enumerate(group_names, start=1):
        traces = groups[group_name]
        unit = traces[0]["unit"]

        for i, t in enumerate(traces):
            sr = t["sampling_rate"]
            freqs, mags = compute_fft(t["data"], sr, db=db)

            label = t["sensor_name"]
            if t.get("source_file"):
                label += f" ({os.path.basename(t['source_file'])})"

            fig.add_trace(
                go.Scattergl(
                    x=freqs, y=mags,
                    mode="lines",
                    name=label,
                    line=dict(color=colors[i % len(colors)], width=1),
                    hovertemplate=f"{t['sensor_name']}<br>%{{x:.1f}} Hz<br>%{{y:.4f}} {y_label}<extra></extra>",
                ),
                row=row_idx, col=1,
            )

        fig.update_yaxes(title_text=f"{unit} — {y_label}", row=row_idx, col=1)
        fig.update_xaxes(title_text="Frequency [Hz]", row=row_idx, col=1)

    height = max(400, 300 * n_groups)
    fig.update_layout(
        title_text=title,
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
    )

    fig.show()


# ---------------------------------------------------------------------------
# Time-domain plotting
# ---------------------------------------------------------------------------

def plot_samples(all_traces: list[dict], title: str = "Bearing Brain Sensor Data"):
    """
    Plot sensor traces using Plotly with subplots grouped by sensor type.

    Each trace dict: {
        "sensor_id": int,
        "sensor_name": str,
        "unit": str,
        "group": str,
        "data": list[float],
        "sampling_rate": float | None,
        "timestamp": str,
        "source_file": str,
    }
    """
    if not all_traces:
        print("No data to plot.")
        return

    # Group traces by their group label
    groups = {}
    for t in all_traces:
        g = t["group"]
        groups.setdefault(g, []).append(t)

    group_names = sorted(groups.keys())
    n_groups = len(group_names)

    fig = make_subplots(
        rows=n_groups, cols=1,
        shared_xaxes=False,
        vertical_spacing=max(0.02, 0.15 / n_groups),
        subplot_titles=group_names,
    )

    colors = [
        "#636EFA", "#EF553B", "#00CC96", "#AB63FA",
        "#FFA15A", "#19D3F3", "#FF6692", "#B6E880",
        "#FF97FF", "#FECB52",
    ]

    for row_idx, group_name in enumerate(group_names, start=1):
        traces = groups[group_name]
        unit = traces[0]["unit"]

        for i, t in enumerate(traces):
            n_samples = len(t["data"])
            sr = t["sampling_rate"]

            # Build x-axis: time in seconds if we have a sampling rate, else sample index
            if sr and sr > 0:
                x = [j / sr for j in range(n_samples)]
                x_label = "Time [s]"
            else:
                x = list(range(n_samples))
                x_label = "Sample index"

            label = t["sensor_name"]
            if t.get("source_file"):
                label += f" ({os.path.basename(t['source_file'])})"

            fig.add_trace(
                go.Scattergl(
                    x=x, y=t["data"],
                    mode="lines",
                    name=label,
                    line=dict(color=colors[i % len(colors)], width=1),
                    hovertemplate=f"{t['sensor_name']}<br>%{{x:.4f}} {x_label}<br>%{{y:.4f}} {unit}<extra></extra>",
                ),
                row=row_idx, col=1,
            )

        fig.update_yaxes(title_text=f"{group_name} [{unit}]", row=row_idx, col=1)
        fig.update_xaxes(title_text=x_label, row=row_idx, col=1)

    height = max(400, 250 * n_groups)
    fig.update_layout(
        title_text=title,
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
    )

    fig.show()


def export_csv(all_traces: list[dict], output_path: str):
    """Export scaled data to CSV."""
    import csv

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source_file", "sensor_id", "sensor_name", "unit",
                         "sampling_rate", "sample_index", "time_s", "value"])

        for t in all_traces:
            sr = t["sampling_rate"]
            for idx, val in enumerate(t["data"]):
                time_s = idx / sr if sr and sr > 0 else ""
                writer.writerow([
                    os.path.basename(t.get("source_file", "")),
                    t["sensor_id"],
                    t["sensor_name"],
                    t["unit"],
                    sr or "",
                    idx,
                    time_s,
                    val,
                ])

    print(f"Exported {sum(len(t['data']) for t in all_traces)} data points to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_file(filepath: str, sensor_filter: list[int] | None, raw: bool,
                  ext_sensor_infos: list | None = None) -> list[dict]:
    """Process one JSON sample file and return trace dicts.
    ext_sensor_infos: optional sensor_infos from an external config file (for sampling rates).
    """
    data = load_sample_file(filepath)
    traces = []

    # Extract device configs (if present)
    device_configs = None
    if not raw and "device_configs" in data:
        dc = data["device_configs"]
        if isinstance(dc, dict) and "configs" in dc:
            device_configs = dc["configs"]

    # Sensor infos: prefer external config, fall back to what's in the sample file
    sensor_infos = ext_sensor_infos or data.get("sensor_infos")
    measurements = data.get("measurements", [])

    for measurement in measurements:
        timestamp = measurement.get("start_timestamp", "")
        samples = measurement.get("samples", [])

        for sample in samples:
            sensor_id = sample.get("sensor_id")
            raw_data = sample.get("data", [])

            if not raw_data:
                continue

            if sensor_filter and sensor_id not in sensor_filter:
                continue

            meta = get_sensor_info(sensor_id)

            if raw:
                scaled_data = raw_data
                unit = "raw"
            else:
                scaled_data = scale_sensor_data(sensor_id, raw_data, device_configs)
                unit = meta["unit"]

            sr = get_sampling_rate(sensor_id, sensor_infos)

            traces.append({
                "sensor_id": sensor_id,
                "sensor_name": meta["name"],
                "unit": unit,
                "group": meta["group"],
                "data": scaled_data,
                "sampling_rate": sr,
                "timestamp": timestamp,
                "source_file": filepath,
            })

    return traces


def main():
    parser = argparse.ArgumentParser(
        description="Scale and plot OE Bearing Brain sensor data"
    )
    parser.add_argument("files", nargs="+", help="JSON sample file(s) to plot")
    parser.add_argument("--raw", action="store_true", help="Plot raw data without scaling")
    parser.add_argument("--sensors", "-s", type=int, nargs="+",
                        help="Only plot these sensor IDs (0-18)")
    parser.add_argument("--config", "-c", type=str,
                        help="Config JSON with sensor_infos (for sampling rates)")
    parser.add_argument("--fft", action="store_true",
                        help="Plot FFT (frequency domain) instead of time domain")
    parser.add_argument("--fft-db", action="store_true",
                        help="Show FFT magnitude in dB scale (implies --fft)")
    parser.add_argument("--export", choices=["csv"], help="Export scaled data to file")
    parser.add_argument("--list-sensors", action="store_true",
                        help="List available sensors in the file(s) and exit")
    args = parser.parse_args()

    if args.fft_db:
        args.fft = True

    # Load external config for sampling rates if provided
    ext_sensor_infos = None
    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        ext_sensor_infos = cfg.get("sensor_infos")
        if ext_sensor_infos:
            print(f"Loaded sampling rates from {args.config} "
                  f"({len(ext_sensor_infos)} sensor(s))")
        else:
            print(f"Warning: {args.config} has no sensor_infos")

    # Expand globs (for shells that don't auto-expand)
    files = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        if expanded:
            files.extend(expanded)
        else:
            files.append(pattern)

    # Process all files
    all_traces = []
    for filepath in files:
        if not os.path.isfile(filepath):
            print(f"Warning: {filepath} not found, skipping.")
            continue
        traces = process_file(filepath, args.sensors, args.raw, ext_sensor_infos)
        all_traces.extend(traces)
        print(f"Loaded {filepath}: {len(traces)} sensor trace(s)")

    if not all_traces:
        print("No sensor data found in the provided file(s).")
        sys.exit(1)

    # List sensors mode
    if args.list_sensors:
        seen = set()
        print(f"\n{'ID':>4}  {'Sensor Name':<28} {'Unit':<6} {'Samples':>8}  File")
        print("-" * 80)
        for t in all_traces:
            key = (t["sensor_id"], t["source_file"])
            if key not in seen:
                seen.add(key)
                print(f"{t['sensor_id']:>4}  {t['sensor_name']:<28} {t['unit']:<6} "
                      f"{len(t['data']):>8}  {os.path.basename(t['source_file'])}")
        return

    # Export mode
    if args.export == "csv":
        out_name = os.path.splitext(os.path.basename(files[0]))[0] + "_scaled.csv"
        export_csv(all_traces, out_name)
        return

    # Build title
    file_names = [os.path.basename(f) for f in files]
    title = f"Bearing Brain: {', '.join(file_names[:3])}"
    if len(file_names) > 3:
        title += f" (+{len(file_names) - 3} more)"

    # Plot
    if args.fft:
        db_label = " [dB]" if args.fft_db else ""
        plot_fft(all_traces, title=f"{title} — FFT{db_label}", db=args.fft_db)
    else:
        scale_label = "Raw" if args.raw else "Scaled to SI"
        plot_samples(all_traces, title=f"{title} [{scale_label}]")


if __name__ == "__main__":
    main()
