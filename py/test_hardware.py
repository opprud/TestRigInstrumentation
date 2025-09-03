#!/usr/bin/env python3
"""
Quick test script to verify connected hardware.
Run this to see what ports are available on your system.
"""

import sys
from pathlib import Path
import serial.tools.list_ports

def main():
    print("🔍 Scanning for connected devices...")
    print("=" * 50)
    
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        print("❌ No serial ports found")
        return
    
    print(f"📍 Found {len(ports)} serial port(s):")
    print()
    
    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device}")
        print(f"   Description: {port.description}")
        print(f"   Hardware ID: {port.hwid}")
        
        if port.vid and port.pid:
            print(f"   VID:PID = {port.vid:04X}:{port.pid:04X}")
            
            # Check for known devices
            if port.vid == 0x2E8A and port.pid == 0x0005:
                print("   🎯 IDENTIFIED: Raspberry Pi Pico (RP2040)")
            elif port.vid == 0x2886 and port.pid == 0x8027:
                print("   🎯 IDENTIFIED: Seeed Studio XIAO RP2040")
            elif port.vid == 0x0403:
                print("   🎯 IDENTIFIED: FTDI USB-Serial Adapter")
                
        if port.manufacturer:
            print(f"   Manufacturer: {port.manufacturer}")
        if port.product:
            print(f"   Product: {port.product}")
        if port.serial_number:
            print(f"   Serial: {port.serial_number}")
            
        print()
    
    print("💡 Tips:")
    print("- Look for RP2040/Pico devices for sensor communication")
    print("- Look for FTDI devices for RS485/Modbus communication")
    print("- Run with --test-rp2040 <port> to test RP2040 communication")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--test-rp2040":
        port = sys.argv[2]
        print(f"🧪 Testing RP2040 communication on {port}")
        try:
            import serial
            import time
            
            with serial.Serial(port, 115200, timeout=2) as ser:
                print("📡 Sending PING...")
                ser.write(b'PING\r\n')
                time.sleep(0.1)
                
                response = ser.readline().decode('ascii', errors='ignore').strip()
                print(f"📨 Response: {response}")
                
                if response.startswith('OK PONG'):
                    print("✅ RP2040 communication successful!")
                    
                    print("📡 Getting device info...")
                    ser.write(b'INFO\r\n')
                    time.sleep(0.1)
                    info = ser.readline().decode('ascii', errors='ignore').strip()
                    print(f"📨 Info: {info}")
                else:
                    print("❌ Unexpected response from device")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
    else:
        main()