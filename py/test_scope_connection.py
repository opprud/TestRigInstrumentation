#!/usr/bin/env python3
"""
Quick test script to verify MSO-X 2024A connection and basic acquisition.
"""
import pyvisa
import sys

def test_connection(ip="169.254.196.182"):
    """Test basic SCPI connection to oscilloscope."""
    print(f"Testing connection to {ip}...")

    try:
        rm = pyvisa.ResourceManager()
        print(f"VISA backend: {rm.visalib}")

        scope = rm.open_resource(f"TCPIP::{ip}::INSTR")
        scope.read_termination = '\n'
        scope.write_termination = '\n'
        scope.timeout = 5000

        # Basic identity query
        idn = scope.query("*IDN?").strip()
        print(f"✓ Connected to: {idn}")

        # Check system status
        scope.write("*CLS")
        err = scope.query("SYST:ERR?").strip()
        print(f"✓ System error status: {err}")

        # Query basic acquisition settings
        acq_type = scope.query(":ACQ:TYPE?").strip()
        print(f"✓ Acquisition type: {acq_type}")

        # Query channel status
        for ch in range(1, 5):
            try:
                disp = scope.query(f":CHAN{ch}:DISP?").strip()
                print(f"✓ Channel {ch} display: {disp}")
            except Exception as e:
                print(f"  Channel {ch} query failed: {e}")

        scope.close()
        print("\n✓ Connection test PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Connection test FAILED: {e}")
        return False

if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "169.254.196.182"
    success = test_connection(ip)
    sys.exit(0 if success else 1)
