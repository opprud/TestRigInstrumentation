#!/usr/bin/env python3
"""
View telemetry data from HDF5 acquisition files
"""
import sys
import h5py
import numpy as np


def print_telemetry(filename):
    """Print telemetry data from an HDF5 file"""

    with h5py.File(filename, "r") as f:
        print(f"=== {filename} ===\n")

        # Check metadata
        if "metadata" in f:
            meta = f["metadata"]
            print("Metadata:")
            telemetry_enabled = meta.attrs.get("telemetry_enabled", False)
            print(f"  Telemetry enabled: {telemetry_enabled}")

            if telemetry_enabled:
                rp2040_port = meta.attrs.get("rp2040_port", "N/A")
                print(f"  RP2040 port: {rp2040_port}")
            print()

        # Check sweeps for telemetry data
        if "sweeps" not in f:
            print("No sweeps found")
            return

        sweeps = f["sweeps"]
        sweep_names = sorted(sweeps.keys())

        # Collect telemetry data
        telemetry_keys = set()
        for sweep_name in sweep_names:
            sweep = sweeps[sweep_name]
            for key in sweep.attrs.keys():
                if key not in ["timestamp_local", "timestamp_utc"]:
                    telemetry_keys.add(key)

        if not telemetry_keys:
            print("No telemetry data found in sweeps")
            return

        print(f"Found telemetry data: {', '.join(sorted(telemetry_keys))}\n")

        # Print summary statistics
        print("="*80)
        print(f"{'Sweep':<12} {'Timestamp':<26} ", end="")

        for key in sorted(telemetry_keys):
            print(f"{key:>12}", end=" ")
        print()
        print("="*80)

        for sweep_name in sweep_names:
            sweep = sweeps[sweep_name]
            timestamp = sweep.attrs.get("timestamp_local", "N/A")

            # Truncate timestamp for display
            if len(timestamp) > 25:
                timestamp = timestamp[:25]

            print(f"{sweep_name:<12} {timestamp:<26}", end=" ")

            for key in sorted(telemetry_keys):
                value = sweep.attrs.get(key, None)
                if value is not None:
                    if isinstance(value, float):
                        print(f"{value:>12.2f}", end=" ")
                    else:
                        print(f"{value:>12}", end=" ")
                else:
                    print(f"{'N/A':>12}", end=" ")
            print()

        # Print statistics if numeric data available
        numeric_keys = []
        for key in sorted(telemetry_keys):
            values = []
            for sweep_name in sweep_names:
                val = sweeps[sweep_name].attrs.get(key)
                if isinstance(val, (int, float)):
                    values.append(val)

            if values:
                numeric_keys.append((key, values))

        if numeric_keys:
            print("\n" + "="*80)
            print("Statistics:")
            print("="*80)
            print(f"{'Parameter':<20} {'Min':>12} {'Max':>12} {'Mean':>12} {'Std':>12}")
            print("-"*80)

            for key, values in numeric_keys:
                arr = np.array(values)
                print(f"{key:<20} {np.min(arr):>12.2f} {np.max(arr):>12.2f} "
                      f"{np.mean(arr):>12.2f} {np.std(arr):>12.2f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python view_telemetry.py <hdf5_file>")
        sys.exit(1)

    print_telemetry(sys.argv[1])
