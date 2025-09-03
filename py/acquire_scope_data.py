#!/usr/bin/env python3
"""
Acquire waveforms from Keysight/Agilent MSO-X 2024A to HDF5 (minimal, robust, short mnemonics).

- Timezone-aware timestamps (Europe/Copenhagen) + UTC
- High-fidelity transfer: WORD (16-bit) preferred; BYTE supported
- Optional acq type: NORM | HRES | AVER (+averages)
- Timestamped output filename when store.timestamped = true
- Debug mode:
    * PyVISA I/O logging to visa_io.log
    * Prints SYST:ERR? entries after commands

HDF5 layout:
  /metadata (attrs)
  /sweeps/sweep_000/<alias>/{time, voltage} (+attrs: scaling, sample_rate, points_reported, source)
"""

import argparse
import json
import os
import time
import logging
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

import numpy as np
import pyvisa
import h5py

# ------------------------ timezone ------------------------
TZ = ZoneInfo("Europe/Copenhagen")
def now_pair():
    return datetime.now(TZ).isoformat(), datetime.now(UTC).isoformat()

# ------------------------ debug ------------------------
DEBUG = False

def visa_enable_logging(path="visa_io.log", level=logging.DEBUG):
    logger = logging.getLogger("pyvisa")
    logger.setLevel(level)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fh = logging.FileHandler(path, mode="w", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)
    try:
        rm = pyvisa.ResourceManager()
        logger.info("PyVISA version: %s", getattr(pyvisa, "__version__", "unknown"))
        logger.info("VISA backend: %s", rm.visalib)
    except Exception as e:
        logger.warning("Could not query VISA backend info: %s", e)

def drain_errors(scope, label=""):
    errs = []
    for _ in range(12):
        try:
            msg = scope.query("SYST:ERR?").strip()
        except Exception as ex:
            errs.append(f"[{label}] SYST:ERR? failed: {ex}")
            break
        if msg.startswith("+0") or msg.startswith("0"):
            break
        errs.append(f"[{label}] {msg}")
    if DEBUG and errs:
        print(*errs, sep="\n")
    return errs

def W(scope, scpi, sleep=0.0):
    scope.write(scpi)
    if sleep: time.sleep(sleep)
    if DEBUG: drain_errors(scope, label=scpi)

def Q(scope, scpi, sleep=0.0):
    resp = scope.query(scpi)
    if sleep: time.sleep(sleep)
    if DEBUG: drain_errors(scope, label=f"{scpi} -> {resp.strip()}")
    return resp

# ------------------------ HDF5 utils ------------------------
def create_dataset(group, name, data, store_cfg):
    kwargs = {}
    if store_cfg.get("compress", "none") == "gzip":
        kwargs["compression"] = "gzip"
        kwargs["compression_opts"] = 4
    if store_cfg.get("chunk", False):
        if hasattr(data, "shape") and len(getattr(data, "shape", ())) == 1 and data.shape[0] > 0:
            kwargs["chunks"] = (max(1, data.shape[0] // 8),)
    return group.create_dataset(name, data=data, **kwargs)

def timestamped_path(base_path: str, when_local_iso: str) -> str:
    root, ext = os.path.splitext(base_path)
    dt = datetime.fromisoformat(when_local_iso)
    ts = dt.strftime("%Y%m%d_%H%M%S")
    return f"{root}_{ts}{ext or '.h5'}"

# ------------------------ VISA resource ------------------------
def open_scope(ip: str):
    if DEBUG:
        visa_enable_logging()
    rm = pyvisa.ResourceManager()
    scope = rm.open_resource(f"TCPIP::{ip}::INSTR")
    scope.read_termination  = '\n'
    scope.write_termination = '\n'
    scope.timeout = 20000
    scope.chunk_size = 1024 * 1024
    scope.clear()
    W(scope, "*CLS")
    print(Q(scope, "*IDN?").strip())
    return scope

# ------------------------ acquisition ------------------------
def arm_and_wait(scope, trigger_sweep="AUTO"):
    """STOP → set sweep → DIGITIZE → wait *OPC?"""
    W(scope, ":STOP")
    try:
        mode = "AUTO" if str(trigger_sweep).upper() == "AUTO" else "NORM"
        W(scope, f":TRIG:SWE {mode}")
    except Exception:
        pass
    W(scope, ":DIGITIZE")
    Q(scope, "*OPC?")

def read_ieee_block(scope, scpi=":WAV:DATA?"):
    """Robust IEEE 488.2 definite-length block read (eats trailing LF)."""
    prev = scope.read_termination
    scope.read_termination = None
    try:
        scope.write(scpi)
        if scope.read_bytes(1) != b'#':
            return scope.read_bytes(scope.bytes_in_buffer)
        nd = int(scope.read_bytes(1).decode('ascii'))
        nlen = int(scope.read_bytes(nd).decode('ascii'))
        payload = scope.read_bytes(nlen)
        try: scope.read_bytes(1)  # trailing LF
        except Exception: pass
        if DEBUG:
            drain_errors(scope, label=f"{scpi} [block {nlen} bytes]")
        return payload
    finally:
        scope.read_termination = prev

def apply_acq_type(scope, acq_cfg):
    """Optional: :ACQ:TYPE NORM|HRES|AVER and :ACQ:AVER N when AVER."""
    acq_type = acq_cfg.get("acq_type", None)
    if not acq_type:
        return
    try:
        val = acq_type.upper()
        W(scope, f":ACQ:TYPE {val}")
        if val.startswith("AVER"):
            W(scope, f":ACQ:AVER {int(acq_cfg.get('averages', 8))}")
    except Exception:
        pass

def read_waveform(scope, src, acq_cfg):
    """
    Minimal, robust Keysight capture for one source:
      set WAV params → (optional ACQ:TYPE) → arm → PRE? → DATA?
    """
    points       = int(acq_cfg["points"])
    fmt          = acq_cfg.get("waveform_format", "WORD").upper()      # WORD preferred
    points_mode  = acq_cfg.get("points_mode", "NORM").upper()          # RAW often not settable
    trigger_mode = acq_cfg.get("trigger_sweep", "AUTO").upper()

    # Waveform transfer setup (short mnemonics)
    W(scope, f":WAV:SOUR {src}")               # CHAN1..CHAN4
    W(scope, f":WAV:FORM {fmt}")               # BYTE | WORD | ASC
    W(scope, f":WAV:POIN {points}")
    try:
        mode_kw = "RAW" if points_mode == "RAW" else "NORM"
        W(scope, f":WAV:POIN:MODE {mode_kw}")
    except Exception:
        pass
    if fmt == "WORD":
        W(scope, ":WAV:UNS 0")                 # signed (WORD)
        W(scope, ":WAV:BYT MSBFirst")          # big-endian
    else:
        W(scope, ":WAV:UNS 1")                 # unsigned (BYTE)

    # Optional acquisition type (HRES/AVER)
    apply_acq_type(scope, acq_cfg)

    # Fresh acquisition and wait
    arm_and_wait(scope, trigger_sweep=trigger_mode) 

    # Scaling (PREamble)
    pre = Q(scope, ":WAV:PRE?").split(',')
    # 0 fmt,1 type,2 points,3 count,4 xinc,5 xorig,6 xref,7 yinc,8 yorig,9 yref
    x_inc = float(pre[4]); x_org = float(pre[5]); x_ref = float(pre[6])
    y_inc = float(pre[7]); y_org = float(pre[8]); y_ref = float(pre[9])

    # Data (robust block read)
    payload = read_ieee_block(scope, ":WAV:DATA?")
    if fmt == "WORD":
        raw = np.frombuffer(payload, dtype=">i2")   # big-endian signed 16-bit
    else:
        raw = np.frombuffer(payload, dtype=np.uint8)

    v  = (raw - y_ref) * y_inc + y_org
    n  = len(v)
    t  = (np.arange(n) - x_ref) * x_inc + x_org
    fs = (1.0 / x_inc) if x_inc > 0 else None

    # Points actually delivered (optional; safe query)
    try:
        pts_reported = int(Q(scope, ":WAV:POIN?"))
    except Exception:
        pts_reported = n

    meta = {
        "x_increment": x_inc, "x_origin": x_org, "x_reference": x_ref,
        "y_increment": y_inc, "y_origin": y_org, "y_reference": y_ref,
        "sample_rate": fs, "points_reported": pts_reported, "source": src
    }
    return t, v, meta

# ------------------------ main loop ------------------------
def acquire_loop(config):
    acq_cfg   = config["acquisition"]
    store_cfg = config["store"]
    channels  = [c for c in config["channels"] if c.get("enabled", True)]

    scope = open_scope(config["scope_ip"])

    # timestamped filename if requested
    ts_local, ts_utc = now_pair()
    out_path = store_cfg["output_file"]
    if store_cfg.get("timestamped", True):
        out_path = timestamped_path(out_path, ts_local)

    with h5py.File(out_path, "w") as h5f:
        # root metadata (minimal)
        meta_grp = h5f.create_group("metadata")
        for k, v in (store_cfg.get("attrs") or {}).items():
            meta_grp.attrs[k] = v
        meta_grp.attrs["created_local"] = ts_local
        meta_grp.attrs["created_utc"]   = ts_utc
        meta_grp.attrs["scope_idn"]     = Q(scope, "*IDN?").strip()
        meta_grp.attrs["script"]        = "acquire_scope_data.py"

        sweeps_grp = h5f.create_group("sweeps")

        samples = int(acq_cfg["samples"])
        interval_sec = float(acq_cfg["interval_sec"])

        for i in range(samples):
            ts_local, ts_utc = now_pair()
            sweep_grp = sweeps_grp.create_group(f"sweep_{i:03d}")
            sweep_grp.attrs["timestamp_local"]  = ts_local
            sweep_grp.attrs["timestamp_utc"]    = ts_utc
            sweep_grp.attrs["points_requested"] = int(acq_cfg["points"])
            sweep_grp.attrs["waveform_format"]  = acq_cfg.get("waveform_format", "WORD")
            sweep_grp.attrs["points_mode"]      = acq_cfg.get("points_mode", "NORM")
            sweep_grp.attrs["trigger_sweep"]    = acq_cfg.get("trigger_sweep", "AUTO")
            acq_type = acq_cfg.get("acq_type", None)
            if acq_type:
                sweep_grp.attrs["acq_type"] = acq_type
                if acq_type.upper().startswith("AVER"):
                    sweep_grp.attrs["averages"] = int(acq_cfg.get("averages", 8))

            for ch in channels:
                alias = ch["name"]; src = ch["source"]; notes = ch.get("notes", "")
                t, v, meta = read_waveform(scope, src, acq_cfg)

                ch_grp = sweep_grp.create_group(alias)
                create_dataset(ch_grp, "time", t, store_cfg)
                create_dataset(ch_grp, "voltage", v, store_cfg)
                for k, val in meta.items():
                    if val is not None:
                        ch_grp.attrs[k] = val
                ch_grp.attrs["notes"] = notes

            print(f"[{ts_local}] Sweep {i+1}/{samples} saved.")
            if i < samples - 1:
                time.sleep(interval_sec)

    scope.close()
    print(f"Saved to: {out_path}")

# ------------------------ CLI ------------------------
def main():
    global DEBUG
    p = argparse.ArgumentParser(description="Acquire waveforms from Keysight/Agilent MSO-X 2024A to HDF5.")
    p.add_argument("config", help="Path to JSON config file")
    p.add_argument("--debug", action="store_true", help="Enable VISA I/O log (visa_io.log) and SYST:ERR? tracing")
    args = p.parse_args()
    DEBUG = args.debug
    if DEBUG:
        print("DEBUG enabled: logging VISA I/O to visa_io.log and tracing SYST:ERR?")
    with open(args.config, "r") as f:
        cfg = json.load(f)
    acquire_loop(cfg)

if __name__ == "__main__":
    main()