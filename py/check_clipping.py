#!/usr/bin/env python3
import sys
import h5py
import numpy as np

if len(sys.argv) < 2:
    print("Usage: python check_clipping.py <hdf5_file>")
    sys.exit(1)

filename = sys.argv[1]

print(f"Analyzing: {filename}\n")

with h5py.File(filename, "r") as f:
    # Check metadata
    print("=== Scope Information ===")
    if "metadata" in f:
        meta = f["metadata"]
        for key in meta.attrs:
            print(f"  {key}: {meta.attrs[key]}")

    # Analyze each sweep
    if "sweeps" not in f:
        print("No sweeps found!")
        sys.exit(1)

    sweeps = f["sweeps"]
    for sweep_name in sorted(sweeps.keys()):
        sweep = sweeps[sweep_name]
        print(f"\n=== {sweep_name} ===")
        if "timestamp_local" in sweep.attrs:
            print(f"  Time: {sweep.attrs['timestamp_local']}")

        for ch_name in sorted(sweep.keys()):
            ch = sweep[ch_name]
            if "voltage" not in ch:
                continue

            v = ch["voltage"][:]
            v_min = np.min(v)
            v_max = np.max(v)
            v_mean = np.mean(v)
            v_std = np.std(v)

            # Check for clipping (common ADC full scale indicators)
            # For WORD format (signed 16-bit), typical range is around ±32767 counts
            # After scaling, check if values are suspiciously constant at extremes
            unique_at_max = len(np.unique(v[v > (v_max - 0.01 * (v_max - v_min))]))
            unique_at_min = len(np.unique(v[v < (v_min + 0.01 * (v_max - v_min))]))

            clipping_warning = ""
            if unique_at_max == 1 or unique_at_min == 1:
                clipping_warning = " ⚠️  POSSIBLE CLIPPING!"

            print(f"\n  Channel: {ch_name}{clipping_warning}")
            print(f"    Min: {v_min:+.6f} V")
            print(f"    Max: {v_max:+.6f} V")
            print(f"    Mean: {v_mean:+.6f} V")
            print(f"    Std: {v_std:.6f} V")
            print(f"    Range: {v_max - v_min:.6f} V")

            # Get channel metadata
            if "source" in ch.attrs:
                print(f"    Source: {ch.attrs['source']}")
            if "x_increment" in ch.attrs:
                print(f"    Sample rate: {1.0/ch.attrs['x_increment']:.0f} Hz")
