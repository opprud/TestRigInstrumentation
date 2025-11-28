#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/au263437/workspace/hih/projekter/ForeverBearing/workspace/TestRig/TestRigInstrumentation/py')

from scope_utils import SocketScope

host = "a-mx2024a-10378.local"
port = 5025

print("Testing SocketScope.query_binary()...")
scope = SocketScope(host, port)

try:
    # Test simple query first
    print("\n1. Testing *IDN?")
    idn = scope.query("*IDN?")
    print(f"   Result: {idn.strip()}")

    # Setup waveform
    print("\n2. Setting up waveform...")
    scope.write(":WAV:SOUR CHAN1")
    scope.write(":WAV:FORM WORD")
    scope.write(":WAV:POIN 1000")
    scope.write(":WAV:UNS 0")
    scope.write(":WAV:BYT MSBFirst")

    print("\n3. Triggering digitize...")
    scope.write(":DIGITIZE")

    print("\n4. Waiting for operation complete...")
    opc = scope.query("*OPC?")
    print(f"   *OPC? = {opc.strip()}")

    print("\n5. Getting preamble...")
    pre = scope.query(":WAV:PRE?")
    print(f"   Preamble (first 50 chars): {pre[:50]}")

    print("\n6. Getting waveform data with query_binary()...")
    data = scope.query_binary(":WAV:DATA?")
    print(f"   SUCCESS! Received {len(data)} bytes")
    print(f"   First 20 bytes: {data[:20]}")

except Exception as e:
    print(f"\n   ERROR: {e}")
    import traceback
    traceback.print_exc()
