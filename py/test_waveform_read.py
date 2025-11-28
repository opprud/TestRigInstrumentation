#!/usr/bin/env python3
import socket

host = "a-mx2024a-10378.local"
port = 5025

def send_cmd(s, cmd):
    """Send command and print what we're doing"""
    print(f"  Sending: {cmd}")
    s.sendall((cmd + "\n").encode("ascii"))

def query_cmd(s, cmd):
    """Send query and read response"""
    print(f"  Query: {cmd}")
    s.sendall((cmd + "\n").encode("ascii"))
    response = s.recv(4096)
    print(f"  Response: {response[:100]}")  # Show first 100 bytes
    return response

print("Testing waveform read with PERSISTENT connection...")
try:
    s = socket.create_connection((host, port), timeout=5.0)
    print("Connected!")

    # Setup waveform acquisition
    send_cmd(s, ":WAV:SOUR CHAN1")
    send_cmd(s, ":WAV:FORM WORD")
    send_cmd(s, ":WAV:POIN 1000")  # Just 1000 points for testing
    send_cmd(s, ":WAV:UNS 0")
    send_cmd(s, ":WAV:BYT MSBFirst")

    print("\n  Triggering digitize...")
    send_cmd(s, ":DIGITIZE")

    print("\n  Waiting for operation complete...")
    opc = query_cmd(s, "*OPC?")

    print("\n  Getting waveform preamble...")
    pre = query_cmd(s, ":WAV:PRE?")

    print("\n  Requesting waveform data...")
    data = query_cmd(s, ":WAV:DATA?")

    print(f"\n  SUCCESS! Received {len(data)} bytes")
    s.close()

except Exception as e:
    print(f"\n  ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("Testing with SEPARATE connections (current implementation)...")

def send_separate(cmd):
    s = socket.create_connection((host, port), timeout=3.0)
    print(f"  Sending: {cmd}")
    s.sendall((cmd + "\n").encode("ascii"))
    s.close()

def query_separate(cmd):
    s = socket.create_connection((host, port), timeout=3.0)
    print(f"  Query: {cmd}")
    s.sendall((cmd + "\n").encode("ascii"))
    response = s.recv(4096)
    print(f"  Response: {response[:100]}")
    s.close()
    return response

try:
    send_separate(":WAV:SOUR CHAN1")
    send_separate(":WAV:FORM WORD")
    send_separate(":WAV:POIN 1000")
    send_separate(":WAV:UNS 0")
    send_separate(":WAV:BYT MSBFirst")
    send_separate(":DIGITIZE")
    query_separate("*OPC?")
    query_separate(":WAV:PRE?")
    data = query_separate(":WAV:DATA?")
    print(f"\n  SUCCESS! Received {len(data)} bytes")
except Exception as e:
    print(f"\n  ERROR: {e}")
    import traceback
    traceback.print_exc()
