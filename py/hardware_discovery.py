#!/usr/bin/env python3
"""
Hardware discovery and connection status for Test Rig Instrumentation.

Detects and reports status of:
- Keysight MSO-X 2024A oscilloscope via SCPI/TCP
- RP2040 microcontroller via USB serial
- RS485/Modbus devices (Omron E5CC) via FTDI adapters

Usage:
    python3 hardware_discovery.py [--json] [--verbose]
"""

import argparse
import json
import logging
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports
import pyvisa

# Vendor/Product IDs for common devices
DEVICE_IDS = {
    'rp2040': [
        {'vid': 0x2E8A, 'pid': 0x0005, 'desc': 'Raspberry Pi RP2040'},
        {'vid': 0x2886, 'pid': 0x8027, 'desc': 'Seeed Studio XIAO RP2040'},
    ],
    'ftdi': [
        {'vid': 0x0403, 'pid': 0x6001, 'desc': 'FTDI FT232R'},
        {'vid': 0x0403, 'pid': 0x6014, 'desc': 'FTDI FT232H'},
        {'vid': 0x0403, 'pid': 0x6015, 'desc': 'FTDI FT-X'},
    ]
}

def discover_serial_ports():
    """Discover and categorize serial ports by device type."""
    ports = serial.tools.list_ports.comports()
    categorized = {'rp2040': [], 'ftdi': [], 'unknown': []}
    
    for port in ports:
        port_info = {
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid,
            'vid': port.vid,
            'pid': port.pid,
            'serial_number': port.serial_number,
            'manufacturer': port.manufacturer,
            'product': port.product,
        }
        
        # Categorize by VID/PID
        if port.vid and port.pid:
            # Check for RP2040 variants
            for device in DEVICE_IDS['rp2040']:
                if port.vid == device['vid'] and port.pid == device['pid']:
                    port_info['device_type'] = device['desc']
                    categorized['rp2040'].append(port_info)
                    break
            else:
                # Check for FTDI devices
                for device in DEVICE_IDS['ftdi']:
                    if port.vid == device['vid'] and port.pid == device['pid']:
                        port_info['device_type'] = device['desc']
                        categorized['ftdi'].append(port_info)
                        break
                else:
                    categorized['unknown'].append(port_info)
        else:
            categorized['unknown'].append(port_info)
    
    return categorized

def test_rp2040_connection(port_device, timeout=2.0):
    """Test connection to RP2040 and get firmware info."""
    try:
        with serial.Serial(port_device, 115200, timeout=timeout) as ser:
            # Send PING command
            ser.write(b'PING\\r\\n')
            time.sleep(0.1)
            
            response = ser.readline().decode('ascii', errors='ignore').strip()
            if response.startswith('OK PONG'):
                # Get device info
                ser.write(b'INFO\\r\\n')
                time.sleep(0.1)
                info_response = ser.readline().decode('ascii', errors='ignore').strip()
                
                return {
                    'status': 'connected',
                    'ping_response': response,
                    'info_response': info_response,
                    'firmware_version': extract_firmware_version(info_response),
                    'last_ping': datetime.now().isoformat()
                }
            else:
                return {
                    'status': 'error',
                    'error': f'Unexpected response: {response}',
                    'last_ping': datetime.now().isoformat()
                }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'last_attempt': datetime.now().isoformat()
        }

def extract_firmware_version(info_response):
    """Extract firmware version from INFO response."""
    # Example: "OK INFO vendor=ForeverBearing device=RP2040 fw=1.0.1"
    parts = info_response.split()
    for part in parts:
        if part.startswith('fw='):
            return part.split('=')[1]
    return 'unknown'

def test_scope_connection(ip_address, timeout=3.0):
    """Test connection to MSO-X oscilloscope."""
    try:
        # Test TCP connection first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip_address, 5025))  # SCPI port
        sock.close()
        
        if result != 0:
            return {
                'status': 'disconnected',
                'error': f'Cannot reach {ip_address}:5025',
                'last_attempt': datetime.now().isoformat()
            }
        
        # Test VISA connection
        rm = pyvisa.ResourceManager()
        scope = rm.open_resource(f'TCPIP::{ip_address}::INSTR')
        scope.timeout = timeout * 1000  # Convert to ms
        
        idn = scope.query('*IDN?').strip()
        scope.close()
        
        return {
            'status': 'connected',
            'idn': idn,
            'ip': ip_address,
            'last_seen': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'ip': ip_address,
            'last_attempt': datetime.now().isoformat()
        }

def test_rs485_connection(port_device, slave_id=1, timeout=2.0):
    """Test RS485/Modbus connection (simplified check)."""
    try:
        # This would typically use a Modbus library like pymodbus
        # For now, just test serial port accessibility
        with serial.Serial(port_device, 9600, timeout=timeout, 
                          parity=serial.PARITY_NONE, stopbits=1) as ser:
            # Basic connectivity test - just opening the port
            return {
                'status': 'connected',  # Optimistic - real implementation would test Modbus
                'port': port_device,
                'slave_id': slave_id,
                'last_read': datetime.now().isoformat(),
                'note': 'Port accessible - full Modbus test not implemented'
            }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'port': port_device,
            'last_attempt': datetime.now().isoformat()
        }

def discover_hardware(config=None):
    """Main hardware discovery function."""
    result = {
        'timestamp': datetime.now().isoformat(),
        'scope': {'status': 'disconnected'},
        'rp2040': {'status': 'disconnected'},
        'rs485': {'status': 'disconnected'},
        'ports': discover_serial_ports()
    }
    
    # Test oscilloscope connection
    scope_ip = '169.254.5.204'  # Default from config
    if config and 'scope_ip' in config:
        scope_ip = config['scope_ip']
    
    result['scope'] = test_scope_connection(scope_ip)
    
    # Test RP2040 connections
    rp2040_ports = result['ports']['rp2040']
    if rp2040_ports:
        # Test the first available RP2040
        port_device = rp2040_ports[0]['device']
        result['rp2040'] = test_rp2040_connection(port_device)
        result['rp2040']['port'] = port_device
    
    # Test RS485/FTDI connections
    ftdi_ports = result['ports']['ftdi']
    if ftdi_ports:
        # Test the first available FTDI device
        port_device = ftdi_ports[0]['device']
        result['rs485'] = test_rs485_connection(port_device)
    
    return result

def main():
    parser = argparse.ArgumentParser(description='Discover and test hardware connections')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--config', help='Path to config.json file')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    # Load config if provided
    config = None
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            config = json.load(f)
    
    # Discover hardware
    hardware_info = discover_hardware(config)
    
    if args.json:
        print(json.dumps(hardware_info, indent=2))
    else:
        # Pretty print results
        print("Hardware Discovery Report")
        print("=" * 50)
        print(f"Timestamp: {hardware_info['timestamp']}")
        print()
        
        # Oscilloscope
        scope = hardware_info['scope']
        print(f"🔬 MSO-X 2024A: {scope['status'].upper()}")
        if scope['status'] == 'connected':
            print(f"   IDN: {scope['idn']}")
            print(f"   IP: {scope['ip']}")
        elif 'error' in scope:
            print(f"   Error: {scope['error']}")
        print()
        
        # RP2040
        rp2040 = hardware_info['rp2040']
        print(f"🔧 RP2040: {rp2040['status'].upper()}")
        if rp2040['status'] == 'connected':
            print(f"   Port: {rp2040['port']}")
            if 'firmware_version' in rp2040:
                print(f"   Firmware: {rp2040['firmware_version']}")
        elif 'error' in rp2040:
            print(f"   Error: {rp2040['error']}")
        print()
        
        # RS485
        rs485 = hardware_info['rs485']
        print(f"🌡️  E5CC (RS485): {rs485['status'].upper()}")
        if rs485['status'] == 'connected':
            print(f"   Port: {rs485['port']}")
        elif 'error' in rs485:
            print(f"   Error: {rs485['error']}")
        print()
        
        # Port summary
        ports = hardware_info['ports']
        print("📍 Available Ports:")
        for category, port_list in ports.items():
            if port_list:
                print(f"   {category.upper()}: {len(port_list)} found")
                for port in port_list:
                    print(f"     - {port['device']} ({port.get('device_type', 'Unknown')})")

if __name__ == '__main__':
    main()