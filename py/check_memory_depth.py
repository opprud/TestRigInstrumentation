#!/usr/bin/env python3
"""
Check scope memory depth with different channel configurations
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

# Check which channels are currently on
print("=== Current channel status ===")
for i in range(1, 5):
    status = scope.query(f":CHAN{i}:DISP?").strip()
    print(f"  CHAN{i}: {'ON' if status == '1' else 'OFF'}")

# Check current acquisition settings
print("\n=== Current acquisition settings ===")
acq_type = scope.query(":ACQuire:TYPE?").strip()
print(f"  Type: {acq_type}")

# Check timebase
timebase = scope.query(":TIMebase:SCALe?").strip()
print(f"  Timebase scale: {timebase} s/div")

# Try to read waveform points for each channel
print("\n=== Available points per channel ===")
scope.write(":WAV:POIN:MODE RAW")
scope.write(":WAV:FORM WORD")

for i in range(1, 5):
    chan = f"CHAN{i}"
    scope.write(f":WAV:SOUR {chan}")

    # Try setting requested points
    scope.write(f":WAV:POIN {cfg['acquisition']['points']}")

    # Read back actual points
    actual = scope.query(":WAV:POIN?").strip()
    print(f"  {chan}: {actual} points (requested {cfg['acquisition']['points']})")

print("\n=== Testing with different channel combinations ===")

# Test with only 1 channel
print("\n1 channel enabled (CHAN1 only):")
scope.write(":CHAN2:DISP OFF")
scope.write(":CHAN3:DISP OFF")
scope.write(":CHAN4:DISP OFF")
scope.write(":CHAN1:DISP ON")
scope.write(":DIGITIZE CHAN1")
scope.query("*OPC?")

scope.write(":WAV:SOUR CHAN1")
scope.write(":WAV:POIN 100000")
actual = scope.query(":WAV:POIN?").strip()
print(f"  Available: {actual} points")

# Test with 2 channels
print("\n2 channels enabled (CHAN1, CHAN2):")
scope.write(":CHAN2:DISP ON")
scope.write(":DIGITIZE CHAN1,CHAN2")
scope.query("*OPC?")

scope.write(":WAV:SOUR CHAN1")
scope.write(":WAV:POIN 100000")
actual = scope.query(":WAV:POIN?").strip()
print(f"  Available: {actual} points")

# Test with 4 channels
print("\n4 channels enabled (all):")
scope.write(":CHAN3:DISP ON")
scope.write(":CHAN4:DISP ON")
scope.write(":DIGITIZE CHAN1,CHAN2,CHAN3,CHAN4")
scope.query("*OPC?")

scope.write(":WAV:SOUR CHAN1")
scope.write(":WAV:POIN 100000")
actual = scope.query(":WAV:POIN?").strip()
print(f"  Available: {actual} points")

print("\n" + "="*60)
print("RECOMMENDATION:")
print(f"  With 4 channels: use points <= {actual}")
print("  For more points: reduce number of enabled channels")
print("="*60)
