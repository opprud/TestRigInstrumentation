#!/usr/bin/env python3
"""
Test script for RS510 VFD with timeout protection.

This script demonstrates the improved timeout and retry logic
to prevent hangs when communicating with hardware on /dev/tty devices.
"""

import argparse
import time
from rs510_vfd_control import RS510VFDController

def test_vfd_with_timeouts(port: str, slave_id: int = 3):
    """Test VFD with built-in timeout protection."""
    print(f"Testing RS510 VFD on {port} with timeout protection...")

    # Create VFD controller with aggressive timeout settings
    vfd = RS510VFDController(port, slave_id, debug=True)

    try:
        print("\n1. Testing connection health...")
        health = vfd.get_health_status()
        print(f"   Initial health: {health['is_connected']}")

        print("\n2. Reading status (with retries)...")
        status = vfd.get_status()
        if status:
            print(f"   Frequency: {status.frequency_cmd_hz} Hz")
            print(f"   Status: {status.run_command.name}")
        else:
            print("   Failed to read status")
            return False

        print("\n3. Testing motor start/stop with timeout protection...")
        print("   Starting motor at 2 Hz...")
        if vfd.start_forward(2.0):
            print("   ✓ Start command sent")
            time.sleep(2)  # Let it run briefly

            print("   Stopping motor...")
            if vfd.stop():
                print("   ✓ Stop command sent")
            else:
                print("   ✗ Stop command failed")
        else:
            print("   ✗ Start command failed")

        print("\n4. Final health check...")
        health = vfd.get_health_status()
        print(f"   Consecutive failures: {health['consecutive_failures']}")
        print(f"   Seconds since success: {health['seconds_since_success']:.1f}")

        return True

    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        vfd.stop()  # Ensure motor is stopped
        return False
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        return False
    finally:
        vfd.disconnect()

def main():
    parser = argparse.ArgumentParser(description="Test RS510 VFD with timeout protection")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/cu.usbserial-FT07T8EH)")
    parser.add_argument("--slave", type=int, default=3, help="Slave ID (default 3)")

    args = parser.parse_args()

    success = test_vfd_with_timeouts(args.port, args.slave)

    if success:
        print("\n✅ Timeout test completed successfully!")
    else:
        print("\n❌ Timeout test failed!")
        exit(1)

if __name__ == "__main__":
    main()