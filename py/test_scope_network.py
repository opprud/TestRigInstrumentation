#!/usr/bin/env python3
import socket

host = "a-mx2024a-10378.local"
ports = [5025, 5555, 4000, 4980]

print(f"Testing TCP connections to {host}...")
for port in ports:
    try:
        s = socket.create_connection((host, port), timeout=2.0)
        print(f"  Port {port}: ✓ CONNECTED")

        # Try to send *IDN?
        s.sendall(b"*IDN?\n")
        response = s.recv(4096)
        print(f"    *IDN? response: {response.decode('ascii', errors='ignore').strip()}")
        s.close()
    except socket.timeout:
        print(f"  Port {port}: ✗ Timeout")
    except ConnectionRefusedError:
        print(f"  Port {port}: ✗ Connection refused")
    except Exception as e:
        print(f"  Port {port}: ✗ {e}")
