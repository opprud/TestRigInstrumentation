#!/usr/bin/env python3
"""
Auto-scale oscilloscope channels based on signal measurements
"""
import sys
sys.path.insert(0, '/Users/au263437/workspace/hih/projekter/ForeverBearing/workspace/TestRig/TestRigInstrumentation/py')

from scope_utils import ScopeManager
import json

# Load config
with open("config.json", "r") as f:
    cfg = json.load(f)

scope_ip = cfg.get("scope_ip")
preferred_port = cfg.get("scope", {}).get("preferred_port")

print("Connecting to scope...")
scope = ScopeManager(preferred_port=preferred_port, scope_ip=scope_ip)

if scope.scope is None:
    print("ERROR: Cannot connect to scope")
    sys.exit(1)

print(f"Connected: {scope.idn()}\n")

# Get enabled channels
channels = [c for c in cfg["channels"] if c.get("enabled", True)]

print("=== Auto-scaling channels ===\n")

for ch in channels:
    source = ch["source"]
    name = ch["name"]

    print(f"{name} ({source}):")

    # Measure the signal
    scope.write(f":MEASure:SOURce {source}")

    try:
        # Get voltage measurements
        vpp = scope.query(":MEASure:VPP?").strip()
        vavg = scope.query(":MEASure:VAVerage?").strip()

        print(f"  Current VPP: {vpp} V")
        print(f"  Current VAVG: {vavg} V")

        # Try to convert to float
        try:
            vpp_val = float(vpp)
            vavg_val = float(vavg)

            # Calculate appropriate vertical scale (8 divisions typically)
            # Scale should be ~VPP/6 to give some headroom
            if vpp_val > 0.001:  # At least 1 mV
                suggested_scale = vpp_val / 6.0

                # Round to nice values
                nice_scales = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
                for scale in nice_scales:
                    if scale >= suggested_scale:
                        suggested_scale = scale
                        break
                else:
                    suggested_scale = nice_scales[-1]

                print(f"  Suggested scale: {suggested_scale} V/div")
                print(f"  Setting vertical scale...")
                scope.write(f":{source}:SCALe {suggested_scale}")

                # Set offset to center the signal
                print(f"  Setting offset to {-vavg_val:.6f} V...")
                scope.write(f":{source}:OFFSet {-vavg_val}")

                print(f"  ✓ Channel auto-scaled")
            else:
                print(f"  ⚠️  Signal too small or not connected")

        except ValueError:
            print(f"  ⚠️  Cannot parse measurements: VPP={vpp}, VAVG={vavg}")

    except Exception as e:
        print(f"  ✗ Error: {e}")

    print()

print("\n=== Auto-scaling complete ===")
print("Check the scope display - signals should now be visible and centered.")
