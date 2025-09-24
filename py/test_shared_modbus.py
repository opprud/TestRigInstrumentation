#!/usr/bin/env python3
"""
Test script for shared Modbus integration

Tests communication with both E5CC and RS510 using the shared connection manager.
This verifies that the FTDI485 adapter can be safely shared between devices.
"""

import argparse
import json
import time
from omron_temp_poll import E5CCTool
from rs510_vfd_control import RS510VFDController
from shared_modbus_manager import reset_shared_modbus_manager


def test_e5cc(port: str, unit_id: int = 4, debug: bool = False):
    """Test E5CC temperature controller communication."""
    print(f"\n🌡️  Testing E5CC (unit {unit_id})...")

    try:
        e5cc = E5CCTool(
            port=port,
            baudrate=9600,
            parity='N',
            bytesize=8,
            stopbits=1,
            timeout=2.0,
            unit_id=unit_id,
            pv_address=0x2000,
            sv_address=0x2103,
            scale=1.0,
            debug=debug
        )

        # Read process value (current temperature)
        pv = e5cc.read_pv_c()
        print(f"   Process Value: {pv:.1f} °C")

        # Read setpoint value
        sv = e5cc.read_sv_c()
        print(f"   Setpoint Value: {sv:.1f} °C")

        e5cc.close()
        print("   ✅ E5CC communication successful")
        return True

    except Exception as e:
        print(f"   ❌ E5CC communication failed: {e}")
        return False


def test_vfd(port: str, unit_id: int = 3, debug: bool = False):
    """Test RS510 VFD communication."""
    print(f"\n⚙️  Testing RS510 VFD (unit {unit_id})...")

    try:
        vfd = RS510VFDController(
            port=port,
            slave_id=unit_id,
            baudrate=9600,
            timeout=2.0,
            debug=debug
        )

        if not vfd.connect():
            print("   ❌ VFD connection failed")
            return False

        # Get VFD status
        status = vfd.get_status()
        print(f"   Frequency Command: {status.frequency_cmd_hz:.2f} Hz")
        print(f"   Run Command: {status.run_command.name}")
        print(f"   Is Running: {status.is_running}")
        print(f"   Fault Code: {status.fault_code}")

        vfd.disconnect()
        print("   ✅ VFD communication successful")
        return True

    except Exception as e:
        print(f"   ❌ VFD communication failed: {e}")
        return False


def test_concurrent_access(port: str, e5cc_unit: int = 4, vfd_unit: int = 3, debug: bool = False):
    """Test that both devices can be accessed in quick succession."""
    print(f"\n🔄 Testing concurrent access...")

    try:
        # Create both device instances
        e5cc = E5CCTool(
            port=port, baudrate=9600, parity='N', bytesize=8, stopbits=1,
            timeout=2.0, unit_id=e5cc_unit, pv_address=0x2000, sv_address=0x2103,
            scale=1.0, debug=debug
        )

        vfd = RS510VFDController(
            port=port, slave_id=vfd_unit, baudrate=9600, timeout=2.0, debug=debug
        )

        # Rapid alternating access
        for i in range(3):
            print(f"   Iteration {i+1}:")

            # Read E5CC
            pv = e5cc.read_pv_c()
            print(f"     E5CC PV: {pv:.1f} °C")

            # Read VFD
            vfd.connect()
            status = vfd.get_status()
            print(f"     VFD Freq: {status.frequency_cmd_hz:.2f} Hz")
            vfd.disconnect()

            time.sleep(0.5)

        e5cc.close()
        print("   ✅ Concurrent access test successful")
        return True

    except Exception as e:
        print(f"   ❌ Concurrent access test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test shared Modbus integration')
    parser.add_argument('--port', required=True, help='FTDI485 serial port (e.g., /dev/tty.usbserial-FTDI485)')
    parser.add_argument('--e5cc-unit', type=int, default=4, help='E5CC unit ID (default: 4)')
    parser.add_argument('--vfd-unit', type=int, default=3, help='VFD unit ID (default: 3)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')

    args = parser.parse_args()

    print("🔧 Test Rig Shared Modbus Integration Test")
    print("=" * 50)
    print(f"Port: {args.port}")
    print(f"E5CC Unit: {args.e5cc_unit}")
    print(f"VFD Unit: {args.vfd_unit}")

    # Reset any existing shared manager
    reset_shared_modbus_manager()

    results = {
        'port': args.port,
        'e5cc_unit': args.e5cc_unit,
        'vfd_unit': args.vfd_unit,
        'tests': {}
    }

    # Test E5CC
    results['tests']['e5cc'] = test_e5cc(args.port, args.e5cc_unit, args.debug)

    # Test VFD
    results['tests']['vfd'] = test_vfd(args.port, args.vfd_unit, args.debug)

    # Test concurrent access
    if results['tests']['e5cc'] and results['tests']['vfd']:
        results['tests']['concurrent'] = test_concurrent_access(
            args.port, args.e5cc_unit, args.vfd_unit, args.debug
        )
    else:
        results['tests']['concurrent'] = False
        print("\n⚠️  Skipping concurrent test due to individual test failures")

    # Summary
    total_tests = len(results['tests'])
    passed_tests = sum(results['tests'].values())

    results['summary'] = {
        'total': total_tests,
        'passed': passed_tests,
        'failed': total_tests - passed_tests,
        'success': passed_tests == total_tests
    }

    print(f"\n📊 Test Summary")
    print(f"   Total Tests: {total_tests}")
    print(f"   Passed: {passed_tests}")
    print(f"   Failed: {total_tests - passed_tests}")

    if results['summary']['success']:
        print("   🎉 All tests passed! Shared Modbus integration is working.")
    else:
        print("   ❌ Some tests failed. Check your Modbus configuration.")

    if args.json:
        print(f"\n{json.dumps(results, indent=2)}")

    # Cleanup
    reset_shared_modbus_manager()

    return 0 if results['summary']['success'] else 1


if __name__ == '__main__':
    exit(main())