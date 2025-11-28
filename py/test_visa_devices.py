#!/usr/bin/env python3
import pyvisa
import json

print("=== Listing all VISA resources ===")
rm = pyvisa.ResourceManager()
resources = rm.list_resources()
print(f"Found {len(resources)} resources:")
for res in resources:
    print(f"  - {res}")

print("\n=== Testing cached device ===")
try:
    with open("scope_cache.json", "r") as f:
        cache = json.load(f)
        cached_host = cache.get("host")
        print(f"Cached host: {cached_host}")

        if cached_host:
            print(f"\nTrying to open: {cached_host}")
            try:
                dev = rm.open_resource(cached_host)
                dev.timeout = 2000
                print(f"  Connected successfully")
                print(f"  Trying *IDN? query...")
                idn = dev.query("*IDN?")
                print(f"  Response: {idn.strip()}")
                dev.close()
            except Exception as e:
                print(f"  Error: {e}")
except FileNotFoundError:
    print("No cache file found")
except Exception as e:
    print(f"Error reading cache: {e}")

print("\n=== Testing each VISA resource for scope identification ===")
for res in resources:
    print(f"\nTesting: {res}")
    try:
        dev = rm.open_resource(res)
        dev.timeout = 2000
        try:
            idn = dev.query("*IDN?")
            print(f"  *IDN?: {idn.strip()}")
            # Check if it looks like an oscilloscope
            if any(keyword in idn.upper() for keyword in ["KEYSIGHT", "MSO", "DSO", "SCOPE", "AGILENT"]):
                print(f"  ✓ THIS LOOKS LIKE A SCOPE!")
        except Exception as e:
            print(f"  No *IDN? response: {e}")
        dev.close()
    except Exception as e:
        print(f"  Cannot open: {e}")
