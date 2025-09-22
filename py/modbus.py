#!/usr/bin/env python3
"""
Minimal Modbus RTU polling example for RS510 VFD
(using pymodbus 3.x).
"""

import time
from pymodbus.client import ModbusSerialClient


def main():
    # Create Modbus RTU client
    client = ModbusSerialClient(
        port="/dev/tty.usbserial-FT07T8EH",  # change to your adapter
        baudrate=9600,                       # RS510 default = 9600 bps
        parity="N",                          # default: None
        stopbits=1,
        bytesize=8,
        timeout=1
    )

    if not client.connect():
        print("❌ Could not connect to RS510 VFD")
        return

    slave_id = 3         # default Modbus address for RS510
    address = 0x2103     # example: Command Frequency (check RS510 Modbus map!)
    #address = 0x2001     # example: Command Frequency (check RS510 Modbus map!)

    try:
        while True:
            #rr = client.read_holding_registers(address=address, count=1, device_id=slave_id)
            rr = client.read_input_registers(address=address, count=1, device_id=slave_id)
            if rr.isError():
                print("⚠️ Modbus error:", rr)
            else:
                value = rr.registers[0]
                print(f"Register {hex(address)} = {value}")
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        client.close()


if __name__ == "__main__":
    main()