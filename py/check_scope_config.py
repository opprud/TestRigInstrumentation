#!/usr/bin/env python3
"""
Check scope configuration and limits
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

print("=== Checking acquisition configuration ===\n")

# Check system status and errors
print("System errors:")
errors = scope.query(":SYSTem:ERRor?").strip()
print(f"  {errors}")

# Clear errors
scope.write("*CLS")

# Try setting waveform points as in config
requested_points = cfg["acquisition"]["points"]
print(f"\nRequested points from config: {requested_points}")

scope.write(":WAV:SOUR CHAN1")
scope.write(f":WAV:POIN {requested_points}")

# Check what was actually set
actual_points = scope.query(":WAV:POIN?").strip()
print(f"Actual points set: {actual_points}")

# Check for errors after setting
errors = scope.query(":SYSTem:ERRor?").strip()
print(f"Errors after setting points: {errors}")

# Check acquisition type
acq_type = scope.query(":ACQuire:TYPE?").strip()
print(f"\nCurrent acquisition type: {acq_type}")

requested_acq_type = cfg["acquisition"]["acq_type"]
print(f"Requested acquisition type: {requested_acq_type}")

scope.write(f":ACQuire:TYPE {requested_acq_type}")
errors = scope.query(":SYSTem:ERRor?").strip()
print(f"Errors after setting acq type: {errors}")

# Check memory depth
print("\n=== Memory depth information ===")
try:
    mem_depth = scope.query(":ACQuire:MDEPth?").strip()
    print(f"Memory depth: {mem_depth}")
except:
    print("Memory depth query not supported")

# Check waveform format
print("\n=== Waveform format ===")
fmt = cfg["acquisition"]["waveform_format"]
print(f"Requested format: {fmt}")
scope.write(f":WAV:FORM {fmt}")

actual_fmt = scope.query(":WAV:FORM?").strip()
print(f"Actual format: {actual_fmt}")

errors = scope.query(":SYSTem:ERRor?").strip()
print(f"Errors: {errors}")

# Check points mode
print("\n=== Points mode ===")
points_mode = cfg["acquisition"]["points_mode"]
print(f"Requested points mode: {points_mode}")

try:
    scope.write(f":WAV:POIN:MODE {points_mode}")
    actual_mode = scope.query(":WAV:POIN:MODE?").strip()
    print(f"Actual points mode: {actual_mode}")
except:
    print("Points mode not supported (using default)")

errors = scope.query(":SYSTem:ERRor?").strip()
print(f"Errors: {errors}")

print("\n=== Available memory/points information ===")
# Try to get maximum points available
try:
    scope.write(":WAV:POIN:MODE NORMal")
    max_norm = scope.query(":WAV:POIN? MAXimum").strip()
    print(f"Max points (NORMAL mode): {max_norm}")
except:
    pass

try:
    scope.write(":WAV:POIN:MODE RAW")
    max_raw = scope.query(":WAV:POIN? MAXimum").strip()
    print(f"Max points (RAW mode): {max_raw}")
except:
    pass

errors = scope.query(":SYSTem:ERRor?").strip()
print(f"\nFinal errors: {errors}")
