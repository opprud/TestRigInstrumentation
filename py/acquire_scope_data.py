#!/usr/bin/env python3
import argparse
import json
import os
import time
import logging
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

import numpy as np
import h5py

from scope_utils import ScopeManager
from telemetry import TelemetryReader, add_telemetry_to_sweep

TZ = ZoneInfo("Europe/Copenhagen")
DEBUG = False


def now_pair():
    return datetime.now(TZ).isoformat(), datetime.now(UTC).isoformat()


def W(scope, cmd, sleep=0.0):
    scope.write(cmd)
    if sleep:
        time.sleep(sleep)


def Q(scope, cmd, sleep=0.0):
    result = scope.query(cmd)
    if sleep:
        time.sleep(sleep)
    return result


def read_ieee_block(scope, cmd):
    """
    Bruger query_binary() fra SocketScope/VisaScope.
    Returnerer renset IEEE 488.2 blok (payload).
    """
    data = scope.query_binary(cmd)
    if not data:
        return data

    if data.startswith(b"#") and len(data) > 2:
        try:
            nd = int(chr(data[1]))
            nlen = int(data[2:2+nd].decode())
            return data[2+nd:2+nd+nlen]
        except:
            return data

    return data


def open_scope_with_autodetect(config):
    scope_cfg = config.get("scope", {})
    preferred_port = scope_cfg.get("preferred_port", None)
    scope_ip = config.get("scope_ip", None)

    mgr = ScopeManager(preferred_port=preferred_port, scope_ip=scope_ip)

    if mgr.scope is None:
        raise RuntimeError("Kan ikke autodetektere scope.")

    # Print IDN
    print(mgr.idn())
    return mgr


def read_waveform(scope, channel_cfg, acq_cfg):
    src = channel_cfg["source"]
    points = int(acq_cfg["points"])
    fmt = acq_cfg.get("waveform_format", "WORD").upper()

    W(scope, f":WAV:SOUR {src}")
    W(scope, f":WAV:FORM {fmt}")
    W(scope, f":WAV:POIN {points}")

    if fmt == "WORD":
        W(scope, ":WAV:UNS 0")
        W(scope, ":WAV:BYT MSBFirst")
    else:
        W(scope, ":WAV:UNS 1")

    W(scope, ":DIGITIZE")
    Q(scope, "*OPC?")
    time.sleep(0.1)  # Small delay to ensure scope is ready

    pre = Q(scope, ":WAV:PRE?").split(",")

    xinc = float(pre[4])
    xorg = float(pre[5])
    xref = float(pre[6])
    yinc = float(pre[7])
    yorg = float(pre[8])
    yref = float(pre[9])

    payload = read_ieee_block(scope, ":WAV:DATA?")
    if fmt == "WORD":
        raw = np.frombuffer(payload, dtype=">i2")
    else:
        raw = np.frombuffer(payload, dtype=np.uint8)

    v = (raw - yref) * yinc + yorg
    n = len(v)
    t = (np.arange(n) - xref) * xinc + xorg
    fs = 1.0 / xinc if xinc > 0 else None

    return t, v, {
        "x_increment": xinc,
        "x_origin": xorg,
        "x_reference": xref,
        "y_increment": yinc,
        "y_origin": yorg,
        "y_reference": yref,
        "sample_rate": fs,
        "points_reported": n,
        "source": src,
    }


def timestamped_path(base, ts_local):
    root, ext = os.path.splitext(base)
    dt = datetime.fromisoformat(ts_local)
    stamp = dt.strftime("%Y%m%d_%H%M%S")
    return f"{root}_{stamp}{ext or '.hdf5'}"


def acquire_loop(config):
    store_cfg = config["store"]
    acq_cfg = config["acquisition"]
    channels = [c for c in config["channels"] if c.get("enabled", True)]

    scope = open_scope_with_autodetect(config)

    # Initialize telemetry reader
    telemetry_cfg = config.get("telemetry", {})
    telemetry = TelemetryReader(telemetry_cfg)

    ts_local, ts_utc = now_pair()
    out_path = store_cfg["output_file"]

    if store_cfg.get("timestamped", True):
        out_path = timestamped_path(out_path, ts_local)

    with h5py.File(out_path, "w") as h5f:

        meta_grp = h5f.create_group("metadata")
        meta_grp.attrs["created_local"] = ts_local
        meta_grp.attrs["created_utc"] = ts_utc
        meta_grp.attrs["scope_idn"] = Q(scope, "*IDN?").strip()

        # Add telemetry metadata
        for key, value in telemetry.get_metadata().items():
            if value is not None:
                meta_grp.attrs[key] = value

        # Add bearing information to metadata
        if "bearing" in config:
            bearing_grp = meta_grp.create_group("bearing")
            for key, value in config["bearing"].items():
                if value and value != "" and value != 0:  # Skip empty values
                    bearing_grp.attrs[key] = value

        # Add lubricant information to metadata
        if "lubricant" in config:
            lubricant_grp = meta_grp.create_group("lubricant")
            for key, value in config["lubricant"].items():
                if value and value != "" and value != 0:  # Skip empty values
                    lubricant_grp.attrs[key] = value

        # Add test parameters to metadata
        if "test_parameters" in config:
            test_grp = meta_grp.create_group("test_parameters")
            for key, value in config["test_parameters"].items():
                if value and value != "" and value != 0:  # Skip empty values
                    test_grp.attrs[key] = value

        sweeps_grp = h5f.create_group("sweeps")

        samples = int(acq_cfg["samples"])
        interval = float(acq_cfg["interval_sec"])

        for i in range(samples):
            ts_local, ts_utc = now_pair()
            sweep = sweeps_grp.create_group(f"sweep_{i:03d}")
            sweep.attrs["timestamp_local"] = ts_local
            sweep.attrs["timestamp_utc"] = ts_utc

            # Read telemetry data for this sweep
            telemetry_data = telemetry.read_all()
            add_telemetry_to_sweep(sweep, telemetry_data)

            for ch in channels:
                alias = ch["name"]
                print(f"  Reading channel {alias} ({ch['source']})...")
                t, v, meta = read_waveform(scope, ch, acq_cfg)

                grp = sweep.create_group(alias)
                grp.create_dataset("time", data=t)
                grp.create_dataset("voltage", data=v)

                for k, val in meta.items():
                    grp.attrs[k] = val

            # Print sweep info with telemetry if available
            info_str = f"[{ts_local}] Sweep {i+1}/{samples}"
            if telemetry_data:
                telem_info = []
                if "load_g" in telemetry_data:
                    telem_info.append(f"Load: {telemetry_data['load_g']:.1f}g")
                if "rpm" in telemetry_data:
                    telem_info.append(f"RPM: {telemetry_data['rpm']:.0f}")
                if "temperature_c" in telemetry_data:
                    telem_info.append(f"Temp: {telemetry_data['temperature_c']:.1f}°C")
                if telem_info:
                    info_str += f" ({', '.join(telem_info)})"
            print(info_str)

            if i < samples - 1:
                time.sleep(interval)

    print(f"Gemte data i: {out_path}")


def main():
    global DEBUG
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="config.json")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    DEBUG = args.debug

    with open(args.config, "r") as f:
        cfg = json.load(f)

    acquire_loop(cfg)


if __name__ == "__main__":
    main()
