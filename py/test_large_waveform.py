#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/au263437/workspace/hih/projekter/ForeverBearing/workspace/TestRig/TestRigInstrumentation/py')

from scope_utils import SocketScope
import time

host = "a-mx2024a-10378.local"
port = 5025

print("Testing with 250,000 points (from config.json)...")
scope = SocketScope(host, port)

try:
    print("\n1. Setting up waveform with 250,000 points...")
    scope.write(":WAV:SOUR CHAN1")
    scope.write(":WAV:FORM WORD")
    scope.write(":WAV:POIN 250000")  # Same as config
    scope.write(":WAV:UNS 0")
    scope.write(":WAV:BYT MSBFirst")

    print("\n2. Triggering digitize...")
    scope.write(":DIGITIZE")

    print("\n3. Waiting for operation complete...")
    start = time.time()
    opc = scope.query("*OPC?")
    elapsed = time.time() - start
    print(f"   *OPC? = '{opc.strip()}' (took {elapsed:.2f} seconds)")

    print("\n4. Getting preamble...")
    pre = scope.query(":WAV:PRE?")
    print(f"   Preamble (first 50 chars): {pre[:50]}")

    print("\n5. Getting waveform data...")
    start = time.time()
    data = scope.query_binary(":WAV:DATA?")
    elapsed = time.time() - start
    print(f"   SUCCESS! Received {len(data)} bytes in {elapsed:.2f} seconds")
    print(f"   First 20 bytes: {data[:20]}")

except Exception as e:
    print(f"\n   ERROR: {e}")
    import traceback
    traceback.print_exc()
