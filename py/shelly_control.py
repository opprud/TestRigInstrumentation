#!/usr/bin/env python3
"""
Shelly Pro 4PM control script via MQTT.
Can be run from any PC with network access to the MQTT broker.

Usage:
  python3 shelly_control.py --status
  python3 shelly_control.py --on 3
  python3 shelly_control.py --off 3
  python3 shelly_control.py --on cpu
  python3 shelly_control.py --off heater

Install: pip install paho-mqtt
"""

import argparse
import json
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)

# --- Config ---
MQTT_HOST     = "185.81.165.190"
MQTT_PORT     = 1883
MQTT_USER     = "mqttuser"
MQTT_PASSWORD = "3711"
DEVICE_ID     = "shellypro4pm-c8f09e84cdf8"

CHANNEL_NAMES = {
    0: "Heater",
    1: "Channel 2",
    2: "Channel 3",
    3: "CPU",
}

# Allow lookup by name
NAME_TO_ID = {v.lower(): k for k, v in CHANNEL_NAMES.items()}
NAME_TO_ID["heater"] = 0
NAME_TO_ID["cpu"]    = 3


def resolve_channel(arg: str) -> int:
    """Resolve channel id from int string or name."""
    try:
        ch = int(arg)
        if ch not in CHANNEL_NAMES:
            print(f"ERROR: Channel {ch} does not exist. Valid: 0-3")
            sys.exit(1)
        return ch
    except ValueError:
        ch = NAME_TO_ID.get(arg.lower())
        if ch is None:
            print(f"ERROR: Unknown channel '{arg}'. Valid names: {list(NAME_TO_ID.keys())}")
            sys.exit(1)
        return ch


def make_client() -> mqtt.Client:
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="shelly_ctrl")
    except AttributeError:
        client = mqtt.Client(client_id="shelly_ctrl")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    return client


def get_status():
    """Fetch and print status of all channels."""
    results = {}
    connected = False
    done = {"v": False}

    def on_connect(c, u, f, rc, *args):
        nonlocal connected
        rc_val = rc if isinstance(rc, int) else rc.value
        if rc_val == 0:
            connected = True
            # Request status for all channels
            for ch in range(4):
                payload = json.dumps({
                    "id": 10 + ch, "src": "shelly_ctrl",
                    "method": "Switch.GetStatus",
                    "params": {"id": ch}
                })
                c.publish(f"{DEVICE_ID}/rpc", payload)
        else:
            print(f"ERROR: Could not connect (rc={rc})")
            sys.exit(1)

    def on_message(c, u, msg, *args):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return

        # status/switch:N
        if "/status/switch:" in topic:
            ch_id = int(topic.split("switch:")[-1])
            results[ch_id] = payload

        # rpc/response (GetStatus reply)
        elif "/rpc/response" in topic:
            result = payload.get("result", {})
            if isinstance(result, dict) and "id" in result and "output" in result:
                results[result["id"]] = result

        # Check if we have all 4
        if len(results) >= 4:
            done["v"] = True

    client = make_client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.subscribe(f"{DEVICE_ID}/#")
    client.loop_start()

    # Wait up to 5 seconds for all responses
    t0 = time.time()
    while not done["v"] and (time.time() - t0) < 5.0:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    print(f"\nShelly Pro 4PM — {DEVICE_ID}")
    print("─" * 50)
    for ch_id in range(4):
        name = CHANNEL_NAMES.get(ch_id, f"Channel {ch_id}")
        data = results.get(ch_id, {})
        output = data.get("output")
        apower = data.get("apower")
        current = data.get("current")
        voltage = data.get("voltage")

        status_str = "ON " if output else "OFF" if output is False else "???"
        power_str  = f"{apower:.1f}W" if apower is not None else "—"
        curr_str   = f"{current*1000:.0f}mA" if current is not None else "—"
        volt_str   = f"{voltage:.1f}V" if voltage is not None else "—"

        print(f"  [{ch_id}] {name:<12} {status_str}   {power_str:>8}  {curr_str:>8}  {volt_str:>8}")

    print()


def set_switch(channel_id: int, on: bool):
    """Turn a channel on or off."""
    name = CHANNEL_NAMES.get(channel_id, f"Channel {channel_id}")
    action = "ON" if on else "OFF"

    connected_flag = {"v": False}
    done_flag = {"v": False}

    def on_connect(c, u, f, rc, *args):
        rc_val = rc if isinstance(rc, int) else rc.value
        if rc_val == 0:
            connected_flag["v"] = True
            payload = json.dumps({
                "id": 42, "src": "shelly_ctrl",
                "method": "Switch.Set",
                "params": {"id": channel_id, "on": on}
            })
            c.publish(f"{DEVICE_ID}/rpc", payload)
        else:
            print(f"ERROR: Could not connect (rc={rc})")
            sys.exit(1)

    def on_message(c, u, msg, *args):
        topic = msg.topic
        # Confirmation via status update or events
        if f"/status/switch:{channel_id}" in topic:
            try:
                data = json.loads(msg.payload.decode())
                output = data.get("output")
                if output is not None:
                    actual = "ON" if output else "OFF"
                    print(f"✓ [{channel_id}] {name}: {actual}")
                    done_flag["v"] = True
            except Exception:
                pass
        elif "/events/rpc" in topic:
            try:
                data = json.loads(msg.payload.decode())
                params = data.get("params", {})
                sw = params.get(f"switch:{channel_id}", {})
                if "output" in sw:
                    actual = "ON" if sw["output"] else "OFF"
                    print(f"✓ [{channel_id}] {name}: {actual}")
                    done_flag["v"] = True
            except Exception:
                pass

    print(f"→ Turning {action}: [{channel_id}] {name}...")

    client = make_client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.subscribe(f"{DEVICE_ID}/#")
    client.loop_start()

    t0 = time.time()
    while not done_flag["v"] and (time.time() - t0) < 5.0:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    if not done_flag["v"]:
        print(f"⚠ Command sent but no confirmation received within 5s")


def main():
    parser = argparse.ArgumentParser(
        description="Shelly Pro 4PM control via MQTT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 shelly_control.py --status
  python3 shelly_control.py --on 3
  python3 shelly_control.py --off 0
  python3 shelly_control.py --on cpu
  python3 shelly_control.py --off heater
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true",
                       help="Show status of all channels")
    group.add_argument("--on",  metavar="CHANNEL",
                       help="Turn channel ON (0-3 or name)")
    group.add_argument("--off", metavar="CHANNEL",
                       help="Turn channel OFF (0-3 or name)")

    args = parser.parse_args()

    if args.status:
        get_status()
    elif args.on is not None:
        ch = resolve_channel(args.on)
        set_switch(ch, True)
    elif args.off is not None:
        ch = resolve_channel(args.off)
        set_switch(ch, False)


if __name__ == "__main__":
    main()
