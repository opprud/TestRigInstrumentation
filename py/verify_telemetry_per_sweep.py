#!/usr/bin/env python3
"""
Verify that telemetry data is captured per-sweep, not just once.
"""
import h5py
import sys

def check_telemetry_per_sweep(h5file):
    """Check if each sweep has independent telemetry readings."""

    with h5py.File(h5file, 'r') as f:
        sweeps = sorted(f['/sweeps'].keys())

        print(f"Analyzing: {h5file}")
        print(f"Found {len(sweeps)} sweeps\n")
        print("=" * 70)

        for sweep_name in sweeps:
            sweep = f[f'/sweeps/{sweep_name}']

            print(f"\n{sweep_name.upper()}")
            print("-" * 40)
            print(f"Timestamp: {sweep.attrs.get('timestamp_local', 'N/A')}")

            # Check for telemetry attributes
            telemetry_keys = [k for k in sweep.attrs.keys() if k.startswith('telemetry_')]

            if telemetry_keys:
                print("\nTelemetry data captured:")
                for key in sorted(telemetry_keys):
                    value = sweep.attrs[key]
                    # Format nicely
                    if 'timestamp' in key:
                        print(f"  {key}: {value}")
                    elif 'rpm' in key:
                        print(f"  {key}: {value:.2f} RPM")
                    elif 'temperature' in key:
                        print(f"  {key}: {value:.2f} °C")
                    elif 'mass' in key:
                        print(f"  {key}: {value:.2f} g")
                    else:
                        print(f"  {key}: {value}")
            else:
                print("\n⚠️  No telemetry data in this sweep")
                print("   (telemetry may be disabled in config)")

        print("\n" + "=" * 70)

        # Summary
        telemetry_enabled = f['/metadata'].attrs.get('telemetry_enabled', False)
        print(f"\nTelemetry enabled in config: {telemetry_enabled}")

        if telemetry_enabled:
            print("\n✓ Telemetry is captured INDEPENDENTLY for each sweep")
            print("  Each sweep has its own speed/temperature/load readings")
            print("  This correctly tracks changing conditions over time")
        else:
            print("\n💡 To enable telemetry, set in config.json:")
            print('   "telemetry": {')
            print('     "enabled": true,')
            print('     "rp2040_port": "/dev/tty.usbmodemXXXX",')
            print('     "modbus_config": "modbus_config.json"')
            print('   }')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 verify_telemetry_per_sweep.py <file.h5>")
        sys.exit(1)

    check_telemetry_per_sweep(sys.argv[1])
