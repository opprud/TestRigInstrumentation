#!/usr/bin/env python3
"""
Probe Modbus registers on RS510 VFD (or similar device).
Scans a range of addresses with both holding and input register reads.
Tested with pymodbus 3.x
"""

import argparse
from pymodbus.client import ModbusSerialClient

def decode_register(addr: int, value: int) -> str:
    """
    Interpret known RS510 registers.
    Returns human-readable string.
    """
    if addr in (0x0B, 0x0C):
        return f"{value/100:.2f} Hz (max/base frequency)"
    elif addr in (0x0E, 0x0F, 0x10, 0x11):
        return f"{value/10:.1f} s (accel/decel)"
    elif addr in (0x13, 0x14):
        return f"{value/100:.2f} Hz (preset freq)"
    elif addr == 0x05:
        return f"{value} (Run source: {'Remote' if value==1 else 'Local'})"
    elif addr == 0x12:
        return f"{value} (parameter-dependent, e.g. carrier freq/limit)"
    else:
        return str(value)

def probe_registers(client, slave_id: int, start: int, end: int):
    print(f"🔎 Probing slave {slave_id} from {hex(start)} to {hex(end)}")
    for addr in range(start, end + 1):
        # Try holding register (function 0x03)
        rr = client.read_holding_registers(address=addr, count=1, device_id=slave_id)
        #rr = client.read_input_registers(address=addr, count=1, device_id=slave_id)
        if not rr.isError():
            print(f"✔️ Holding {hex(addr)} = {rr.registers[0]}")
            
            raw = rr.registers[0]
            decoded = decode_register(addr, raw)
            print(f"✔️ Holding {hex(addr)} = {raw} → {decoded}")
        # Try input register (function 0x04)
        rr = client.read_input_registers(address=addr, count=1, device_id=slave_id)
        if not rr.isError():
            print(f"✔️ Input   {hex(addr)} = {rr.registers[0]}")


def main():
    parser = argparse.ArgumentParser(description="Probe Modbus registers on RS510 VFD")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--baudrate", type=int, default=9600, help="Baudrate (default=9600)")
    parser.add_argument("--slave", type=int, default=3, help="Slave ID (default=3)")
    parser.add_argument("--start", type=lambda x: int(x, 0), default=0x2000, help="Start address (default=0x2000)")
    parser.add_argument("--end", type=lambda x: int(x, 0), default=0x210F, help="End address (default=0x210F)")
    args = parser.parse_args()

    client = ModbusSerialClient(
        port=args.port,
        baudrate=args.baudrate,
        parity="N",
        stopbits=1,
        bytesize=8,
        timeout=1
    )

    if not client.connect():
        print("❌ Could not connect to RS510 VFD")
        return

    try:
        probe_registers(client, args.slave, args.start, args.end)
    finally:
        client.close()


if __name__ == "__main__":
    main()