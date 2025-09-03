#!/usr/bin/env python3
"""
RP2040 serial client for HX711 load cell & tachometer.
Prints results as raw text or as json foirmatted text - could be piped to a file
Author : Morten Opprud (& GPT-5)
Notes: Part of tool suite for executing forever bearing experiments

Protocol (ASCII, CRLF-terminated):
  PING                 -> OK PONG
  INFO                 -> OK INFO vendor=... device=... fw=...
  LOAD?                -> OK LOAD mass_g=<float> raw=<int> ts=<unix_ms>
  TARE                 -> OK TARE
  SPEED?               -> OK SPEED rpm=<float> period_ms=<float> pulses=<u32> ts=<unix_ms>
  SETCAL <slope> <tare>-> OK SETCAL
  CAL?                 -> OK CAL slope=<float> tare=<int>
  SETTIME <unix_ms>    -> OK SETTIME
  SETPPR <ppr>         -> OK SETPPR
  PPR?                 -> OK PPR ppr=<int>

Subcommands:
  ping | info | tare | load | speed | setcal | calibrate | settime | setppr | cal

Use --json to emit JSON for automation.
"""

import argparse
import sys
import time
import json
from datetime import datetime, timezone

import serial  # pyserial


# ------------------ serial helpers ------------------

def open_port(port, baud=115200, timeout=1.0):
    return serial.Serial(port=port, baudrate=baud, timeout=timeout)


def send_cmd(ser, cmd, expect_prefix=("OK", "ERR"), timeout=None):
    """
    Send a single-line command, return tuple (status, head, payload_str).
    status is 'OK' or 'ERR' or None if timed out.
    """
    if timeout is None:
        timeout = ser.timeout or 1.0

    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode("ascii"))
    ser.flush()

    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline()  # reads until '\n' or timeout
        if not line:
            continue
        text = line.decode("ascii", errors="replace").strip()
        if not text:
            continue
        parts = text.split(" ", 2)
        head = parts[0]
        if head in expect_prefix:
            arg = parts[1] if len(parts) > 1 else ""
            payload = parts[2] if len(parts) > 2 else ""
            return head, arg, payload
    return None, None, None


def parse_kv(s):
    """Parse 'k=v k2=v2 ...' into dict of strings."""
    out = {}
    if not s:
        return out
    for token in s.split():
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


def as_number(v):
    try:
        if v is None:
            return None
        if "." in v or "e" in v or "E" in v:
            return float(v)
        return int(v)
    except Exception:
        return v


def print_out(obj, as_json=False):
    if as_json:
        print(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    else:
        if isinstance(obj, dict):
            # pretty print dict
            for k, v in obj.items():
                print(f"{k}: {v}")
        else:
            print(obj)


# ------------------ convenience ops ------------------

def read_load(ser):
    stat, head, payload = send_cmd(ser, "LOAD?")
    if stat != "OK":
        raise RuntimeError(f"LOAD? failed: {stat} {head} {payload}")
    kv = parse_kv((head + " " + payload).strip())
    # normalize
    for k in ("mass_g", "raw", "ts"):
        if k in kv:
            kv[k] = as_number(kv[k])
    return {"status": "OK", "type": "LOAD", **kv}


def do_tare(ser):
    stat, head, payload = send_cmd(ser, "TARE")
    if stat != "OK":
        raise RuntimeError(f"TARE failed: {stat} {head} {payload}")
    return {"status": "OK", "type": "TARE"}


def set_cal(ser, slope, tare):
    stat, head, payload = send_cmd(ser, f"SETCAL {slope:.9g} {int(tare)}")
    if stat != "OK":
        raise RuntimeError(f"SETCAL failed: {stat} {head} {payload}")
    return {"status": "OK", "type": "SETCAL", "slope": slope, "tare": int(tare)}


def get_cal(ser):
    stat, head, payload = send_cmd(ser, "CAL?")
    if stat != "OK":
        raise RuntimeError(f"CAL? failed: {stat} {head} {payload}")
    kv = parse_kv((head + " " + payload).strip())
    for k in ("slope", "tare"):
        if k in kv:
            kv[k] = as_number(kv[k])
    return {"status": "OK", "type": "CAL", **kv}


def set_time_now(ser, unix_ms=None):
    if unix_ms is None:
        unix_ms = int(time.time() * 1000.0)
    stat, head, payload = send_cmd(ser, f"SETTIME {unix_ms}")
    if stat != "OK":
        raise RuntimeError(f"SETTIME failed: {stat} {head} {payload}")
    return {"status": "OK", "type": "SETTIME", "unix_ms": unix_ms}


def read_speed(ser):
    stat, head, payload = send_cmd(ser, "SPEED?")
    if stat != "OK":
        raise RuntimeError(f"SPEED? failed: {stat} {head} {payload}")
    kv = parse_kv((head + " " + payload).strip())
    for k in ("rpm", "period_ms", "pulses", "ts"):
        if k in kv:
            kv[k] = as_number(kv[k])
    return {"status": "OK", "type": "SPEED", **kv}


def set_ppr(ser, ppr):
    stat, head, payload = send_cmd(ser, f"SETPPR {int(ppr)}")
    if stat != "OK":
        raise RuntimeError(f"SETPPR failed: {stat} {head} {payload}")
    return {"status": "OK", "type": "SETPPR", "ppr": int(ppr)}


def get_ppr(ser):
    stat, head, payload = send_cmd(ser, "PPR?")
    if stat != "OK":
        raise RuntimeError(f"PPR? failed: {stat} {head} {payload}")
    kv = parse_kv((head + " " + payload).strip())
    if "ppr" in kv:
        kv["ppr"] = as_number(kv["ppr"])
    return {"status": "OK", "type": "PPR", **kv}


# ------------------ CLI ------------------

def main():
    ap = argparse.ArgumentParser(description="RP2040 serial client (HX711 + tachometer)")
    ap.add_argument("--port", required=True, help="Serial device, e.g. /dev/tty.usbmodemXXXX or COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--json", action="store_true", help="Emit JSON")

    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    sub.add_parser("info")
    sub.add_parser("tare")
    sub.add_parser("load")
    sub.add_parser("speed")
    sub.add_parser("cal")  # CAL?

    p_setcal = sub.add_parser("setcal", help="Send SETCAL with explicit values")
    p_setcal.add_argument("--slope", type=float, required=True, help="grams per count")
    p_setcal.add_argument("--tare",  type=int,   required=True, help="raw tare offset")

    p_cal = sub.add_parser("calibrate", help="Guided calibration with known weight")
    p_cal.add_argument("--weight-g", type=float, required=True, help="known calibration weight in grams")
    p_cal.add_argument("--settle-sec", type=float, default=5.0, help="settling time after putting/removing weight")

    p_settime = sub.add_parser("settime", help="Set device epoch")
    p_settime.add_argument("--unix-ms", type=int, default=None, help="UNIX epoch in ms (defaults to host now)")

    p_setppr = sub.add_parser("setppr", help="Set pulses-per-revolution for tach")
    p_setppr.add_argument("--ppr", type=int, required=True)

    args = ap.parse_args()
    ser = open_port(args.port, args.baud, args.timeout)

    try:
        if args.cmd == "ping":
            stat, h, p = send_cmd(ser, "PING")
            out = {"status": stat or "TIMEOUT", "type": "PING", "arg": h, "payload": p}

        elif args.cmd == "info":
            stat, h, p = send_cmd(ser, "INFO")
            kv = parse_kv((h + " " + p).strip())
            out = {"status": stat or "TIMEOUT", "type": "INFO", **kv}

        elif args.cmd == "tare":
            out = do_tare(ser)

        elif args.cmd == "load":
            out = read_load(ser)

        elif args.cmd == "speed":
            out = read_speed(ser)

        elif args.cmd == "cal":
            out = get_cal(ser)

        elif args.cmd == "setcal":
            out = set_cal(ser, args.slope, args.tare)

        elif args.cmd == "calibrate":
            # Tare with no load
            _ = do_tare(ser)
            # Ask user to place weight; wait
            time.sleep(args.settle_sec)
            loaded = read_load(ser)
            raw_loaded = int(loaded.get("raw", 0))
            # Ask user to remove weight; wait
            time.sleep(args.settle_sec)
            tare_read = read_load(ser)
            tare_raw = int(tare_read.get("raw", 0))
            delta = raw_loaded - tare_raw
            if delta == 0:
                raise RuntimeError("Calibration failed: raw delta is zero. Check wiring/weight.")
            slope = float(args.weight_g) / float(delta)
            _ = set_cal(ser, slope, tare_raw)
            out = {
                "status": "OK",
                "type": "CALIBRATE",
                "weight_g": args.weight_g,
                "raw_loaded": raw_loaded,
                "tare_raw": tare_raw,
                "delta": delta,
                "slope": slope
            }

        elif args.cmd == "settime":
            out = set_time_now(ser, args.unix_ms)

        elif args.cmd == "setppr":
            out = set_ppr(ser, args.ppr)

        else:
            raise SystemExit("unknown command")

        print_out(out, as_json=args.json)

    except Exception as e:
        if args.json:
            print(json.dumps({"status": "ERROR", "error": str(e)}))
        else:
            print("ERROR:", e, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()