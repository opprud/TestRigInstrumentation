#!/usr/bin/env python3
import argparse
import json
import os
import time
import logging
import math
import asyncio
import threading
from datetime import datetime, UTC
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import h5py

from scope_utils import ScopeManager


TZ = ZoneInfo("Europe/Copenhagen")
DEBUG = False


def now_pair():
    return datetime.now(TZ).isoformat(), datetime.now(UTC).isoformat()


def W(scope, cmd, sleep=0.0, retries=5):
    last = None
    for attempt in range(retries):
        try:
            scope.write(cmd)
            if sleep:
                time.sleep(sleep)
            return
        except (ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError) as e:
            last = e
            # exponential-ish backoff
            time.sleep(0.5 * (2 ** attempt))
    raise last


def Q(scope, cmd, sleep=0.0, retries=5):
    last = None
    for attempt in range(retries):
        try:
            result = scope.query(cmd)
            if sleep:
                time.sleep(sleep)
            return result
        except (ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError) as e:
            last = e
            time.sleep(0.5 * (2 ** attempt))
    raise last
    

def read_ieee_block(scope, cmd, retries=5, base_sleep=0.5):
    """
    Bruger query_binary() fra SocketScope/VisaScope.
    Returnerer renset IEEE 488.2 blok (payload).

    Retry'er ved midlertidige socket-fejl (ConnectionRefused/Reset/Timeout/OSError).
    """
    last_exc = None

    for attempt in range(retries):
        try:
            data = scope.query_binary(cmd)
            break
        except (ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError) as e:
            last_exc = e
            time.sleep(base_sleep * (2 ** attempt))
    else:
        # exhausted retries
        raise last_exc

    if not data:
        return data

    if data.startswith(b"#") and len(data) > 2:
        try:
            nd = int(chr(data[1]))
            nlen = int(data[2:2 + nd].decode())
            return data[2 + nd:2 + nd + nlen]
        except Exception:
            return data

    return data

def open_scope_with_pyvisa(config: dict):
    """
    Open scope exactly like UI/api_server.py does (PyVISA TCPIP::IP::INSTR).
    Reads IP from either:
      - config["scope_ip"]   (UI style)
      - config["scope"]["ip"/"host"/"scope_ip"] (nested style)
    """
    try:
        import pyvisa
    except Exception:
        return None

    scope_cfg = config.get("scope", {}) or {}

    ip = (
        config.get("scope_ip")  # <-- IMPORTANT: matches api_server.py
        or scope_cfg.get("ip")
        or scope_cfg.get("host")
        or scope_cfg.get("scope_ip")
    )
    if not ip:
        return None

    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(f"TCPIP::{ip}::INSTR")

    inst.timeout = int(scope_cfg.get("timeout_ms", 20000))
    inst.write_termination = "\n"
    inst.read_termination = "\n"

    try:
        inst.write("*CLS")
        inst.query("*OPC?")
    except Exception:
        pass

    try:
        print(inst.query("*IDN?").strip())
    except Exception:
        pass

    return inst

def visa_query_text(inst, cmd: str, timeout_ms: int = 15000, max_bytes: int = 8192) -> str:
    """
    Robust SCPI text query for PyVISA without using read_raw() (can throw VI_ERROR_IO on pyvisa-py).
    Uses read_bytes(..., break_on_termchar=True) so we stop on read_termination (\\n).
    """
    old_timeout = inst.timeout
    try:
        inst.timeout = timeout_ms

        # Ensure session uses newline terminations (you already set these on open)
        # inst.write_termination = "\n"
        # inst.read_termination = "\n"

        # Send query
        if not cmd.endswith("\n"):
            cmd += "\n"
        inst.write(cmd.rstrip("\n"))

        # Read until termination char (typically '\n')
        data = inst.read_bytes(max_bytes, break_on_termchar=True)

        # read_bytes can return bytearray/bytes
        if isinstance(data, bytearray):
            data = bytes(data)

        return data.decode(errors="ignore").strip()
    finally:
        inst.timeout = old_timeout
        
def open_scope_with_autodetect(config):
    scope_cfg = config.get("scope", {}) or {}

    # If scope_ip is present (UI style), ALWAYS use PyVISA on TCPIP::<ip>::INSTR
    ip = config.get("scope_ip")
    if ip:
        import pyvisa
        # rm = pyvisa.ResourceManager("@py")
        rm = pyvisa.ResourceManager()   # default (typisk @ivi hvis Keysight/NI-VISA er installeret)
        
        port = int(scope_cfg.get("preferred_port", 5025))
        inst = rm.open_resource(f"TCPIP::{ip}::{port}::SOCKET")

        inst.timeout = int(scope_cfg.get("timeout_ms", 20000))
        inst.write_termination = "\n"
        inst.read_termination = "\n"

        try:
            inst.write("*CLS")
            inst.query("*OPC?")
        except Exception:
            pass

        try:
            print(inst.query("*IDN?").strip())
        except Exception:
            pass

        return inst

    # Fallback: old autodetect (preferred_port 5025 / ScopeManager)
    preferred_port = scope_cfg.get("preferred_port", None)
    mgr = ScopeManager(preferred_port=preferred_port)

    if mgr.scope is None:
        raise RuntimeError("Kan ikke autodetektere scope.")

    print(mgr.idn())
    return mgr
    
def visa_query_number(inst, cmd: str, timeout_ms: int = 15000) -> str:
    old_timeout = inst.timeout
    try:
        inst.timeout = timeout_ms
        # inst.query() virker for *OPC? hos dig, så vi bruger den her.
        return inst.query(cmd).strip()
    finally:
        inst.timeout = old_timeout
        
def socket_query_line(ip: str, port: int, cmd: str, timeout_sec: float = 3.0) -> str:
    import socket
    s = socket.create_connection((ip, port), timeout=timeout_sec)
    s.settimeout(timeout_sec)
    try:
        s.sendall((cmd.strip() + "\n").encode("ascii", errors="ignore"))
        chunks = []
        while True:
            buf = s.recv(4096)
            if not buf:
                break
            chunks.append(buf)
            if b"\n" in buf:
                break
        return b"".join(chunks).decode(errors="ignore").strip()
    finally:
        try:
            s.close()
        except Exception:
            pass
            
def socket_capture_waveform(ip: str, port: int, src: str, points: int, fmt: str, timeout_sec: float = 15.0):
    import socket
    import numpy as np
    import time

    def send(s, cmd):
        s.sendall((cmd + "\n").encode("ascii", errors="ignore"))

    def recv_first_then_drain(s, first_timeout: float, drain_timeout: float) -> bytes:
        """
        Read first bytes with longer timeout, then drain any remaining bytes
        with short timeout. Does NOT require newline to terminate.
        """
        # First chunk
        s.settimeout(first_timeout)
        first = s.recv(4096)
        if not first:
            return b""

        chunks = [first]

        # Drain
        s.settimeout(drain_timeout)
        while True:
            try:
                buf = s.recv(4096)
                if not buf:
                    break
                chunks.append(buf)
            except TimeoutError:
                break

        return b"".join(chunks)

    def query_text(s, cmd) -> str:
        send(s, cmd)
        data = recv_first_then_drain(s, first_timeout=timeout_sec, drain_timeout=0.2)
        return data.decode(errors="ignore").strip()

    def query_opc(s):
        # *OPC? should return quickly; still use robust read
        return query_text(s, "*OPC?")

    def recv_exact(s, n):
        chunks = []
        remaining = n
        while remaining > 0:
            buf = s.recv(min(65536, remaining))
            if not buf:
                raise ConnectionError("Socket closed during recv_exact")
            chunks.append(buf)
            remaining -= len(buf)
        return b"".join(chunks)

    def query_ieee_block_payload(s, cmd) -> bytes:
        """
        Send query that returns IEEE 488.2 definite-length block and return payload only.
        """
        send(s, cmd)

        # Read "#<nd>"
        s.settimeout(timeout_sec)
        first2 = recv_exact(s, 2)
        if not first2.startswith(b"#"):
            # not a block; best-effort drain
            rest = recv_first_then_drain(s, first_timeout=0.5, drain_timeout=0.2)
            return first2 + rest

        nd = int(chr(first2[1]))
        len_bytes = recv_exact(s, nd)
        nlen = int(len_bytes.decode("ascii"))
        payload = recv_exact(s, nlen)

        # optional trailing newline (best-effort)
        try:
            s.settimeout(0.2)
            _ = s.recv(2)
        except Exception:
            pass

        return payload

    s = socket.create_connection((ip, port), timeout=timeout_sec)
    s.settimeout(timeout_sec)
    try:
        # Fresh-state
        send(s, "*CLS")
        query_opc(s)

        # Source select
        send(s, f":WAV:SOUR {src}")

        # Use socket-known commands (original CLI style)
        send(s, f":WAV:FORM {fmt}")
        send(s, f":WAV:POIN {points}")

        if fmt == "WORD":
            send(s, ":WAV:UNS 0")
            send(s, ":WAV:BYT MSBFirst")
        else:
            send(s, ":WAV:UNS 1")

        # Digitize + wait
        send(s, ":DIGITIZE")
        query_opc(s)

        # Preamble (robust read, no newline assumption)
        pre_line = query_text(s, ":WAV:PRE?")
        # Optional: if empty, ask error queue once (helps debug)
        if not pre_line:
            err = query_text(s, ":SYST:ERR?")
            raise RuntimeError(f"Empty PRE? response. SYST:ERR?={err}")

        pre = pre_line.split(",")
        xinc = float(pre[4])
        xorg = float(pre[5])
        xref = float(pre[6])
        yinc = float(pre[7])
        yorg = float(pre[8])
        yref = float(pre[9])

        # Data block
        payload = query_ieee_block_payload(s, ":WAV:DATA?")
        if fmt == "WORD":
            raw = np.frombuffer(payload, dtype=">i2")
        else:
            raw = np.frombuffer(payload, dtype=np.uint8)

        return raw, xinc, xorg, xref, yinc, yorg, yref

    finally:
        try:
            s.close()
        except Exception:
            pass
            
def read_waveform(scope, channel_cfg, acq_cfg):
    src = channel_cfg["source"]
    points = int(acq_cfg["points"])
    fmt = acq_cfg.get("waveform_format", "WORD").upper()

    scope_cfg = acq_cfg.get("_scope_cfg") or {}
    ip = scope_cfg.get("ip") or scope_cfg.get("scope_ip")
    port = int(scope_cfg.get("preferred_port", 5025))

    # socket-only capture (UI-sekvens på én TCP session)
    raw, xinc, xorg, xref, yinc, yorg, yref = socket_capture_waveform(
        ip=ip, port=port, src=src, points=points, fmt=fmt, timeout_sec=15.0
    )

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
    return f"{root}_{stamp}{ext or '.h5'}"

def make_run_id() -> str:
    # Same timezone as the rest of the script
    return datetime.now(TZ).strftime("%Y%m%d_%H%M%S")


def _apply_profile_to_scope_cfg(scope_cfg: dict, profile_cfg: dict) -> dict:
    """
    Map test-profile.json -> acquire_scope_data acquisition config
    so scope sampling matches test duration + interval + scope_points.
    """
    out = json.loads(json.dumps(scope_cfg))  # simple deep copy

    duration_min = (
        profile_cfg.get("duration_minutes")
        or (profile_cfg.get("test_parameters", {}) or {}).get("duration_minutes")
        or 0
    )
    duration_sec = float(duration_min) * 60.0

    prof_acq = profile_cfg.get("acquisition", {}) or {}
    interval_sec = prof_acq.get("interval_sec")
    if interval_sec is None:
        interval_sec = out.get("acquisition", {}).get("interval_sec", 1.0)
    interval_sec = float(interval_sec) if float(interval_sec) > 0 else 1.0

    samples = 1
    if duration_sec > 0:
        samples = max(1, int(math.ceil(duration_sec / interval_sec)))

    out.setdefault("acquisition", {})
    out["acquisition"]["interval_sec"] = interval_sec
    out["acquisition"]["samples"] = samples

    if "scope_points" in prof_acq and prof_acq["scope_points"] is not None:
        out["acquisition"]["points"] = int(prof_acq["scope_points"])

    if "waveform_format" in prof_acq and prof_acq["waveform_format"]:
        out["acquisition"]["waveform_format"] = str(prof_acq["waveform_format"])

    return out
    
def open_scope_session(config):
    """
    Open a fresh PyVISA session to the scope (UI-like behavior: open -> use -> close per sweep).
    Uses scope_ip + preferred_port (5025) from config.
    """
    import pyvisa

    scope_cfg = config.get("scope", {}) or {}
    ip = config.get("scope_ip")
    if not ip:
        raise RuntimeError("scope_ip mangler i config.json")

    port = int(scope_cfg.get("preferred_port", 5025))

    rm = pyvisa.ResourceManager()  # will still be pyvisa-py in your env, but fresh session helps
    inst = rm.open_resource(f"TCPIP::{ip}::{port}::SOCKET")

    inst.timeout = int(scope_cfg.get("timeout_ms", 20000))
    inst.write_termination = "\n"
    inst.read_termination = "\n"

    # Fresh-state like API does
    try:
        inst.write("*CLS")
        inst.query("*OPC?")
    except Exception:
        pass

    return inst
    
def _query_scope_settings(ip: str, port: int, channels: list) -> dict:
    """
    Query scope for current hardware settings.
    Returns dict with timebase, trigger, acq and per-channel settings.
    """
    settings = {}
    try:
        # Timebase
        settings["timebase_range"]     = socket_query_line(ip, port, ":TIM:RANG?")
        settings["timebase_scale"]     = socket_query_line(ip, port, ":TIM:SCAL?")
        settings["timebase_position"]  = socket_query_line(ip, port, ":TIM:POS?")
        settings["timebase_reference"] = socket_query_line(ip, port, ":TIM:REF?")
        settings["timebase_mode"]      = socket_query_line(ip, port, ":TIM:MODE?")

        # Trigger
        settings["trigger_coupling"]   = socket_query_line(ip, port, ":TRIG:COUP?")
        settings["trigger_level"]      = socket_query_line(ip, port, ":TRIG:LEV?")
        settings["trigger_slope"]      = socket_query_line(ip, port, ":TRIG:SLOP?")

        # Acquisition
        settings["acq_type"]           = socket_query_line(ip, port, ":ACQ:TYPE?")
        settings["acq_mode"]           = socket_query_line(ip, port, ":ACQ:MODE?")
        try:
            settings["acq_sample_rate"] = socket_query_line(ip, port, ":ACQ:SRAT?")
        except Exception:
            pass
        settings["acq_points"]         = socket_query_line(ip, port, ":ACQ:POIN?")

    except Exception as e:
        if DEBUG:
            print(f"[scope_settings] Error querying global settings: {e}")

    # Per-channel settings
    ch_settings = {}
    for ch in channels:
        src = ch["source"]   # e.g. "CHAN1"
        alias = ch["name"]
        try:
            ch_settings[alias] = {
                "source":           src,
                "bandwidth_limit":  socket_query_line(ip, port, f":{src}:BWL?"),
                "coupling":         socket_query_line(ip, port, f":{src}:COUP?"),
                "display":          socket_query_line(ip, port, f":{src}:DISP?"),
                "impedance":        socket_query_line(ip, port, f":{src}:IMP?"),
                "invert":           socket_query_line(ip, port, f":{src}:INV?"),
                "offset":           socket_query_line(ip, port, f":{src}:OFFS?"),
                "probe_attenuation":socket_query_line(ip, port, f":{src}:PROB?"),
                "range":            socket_query_line(ip, port, f":{src}:RANG?"),
                "scale":            socket_query_line(ip, port, f":{src}:SCAL?"),
                "units":            socket_query_line(ip, port, f":{src}:UNIT?"),
            }
        except Exception as e:
            if DEBUG:
                print(f"[scope_settings] Error querying {src}: {e}")
            ch_settings[alias] = {"source": src}

    settings["channels"] = ch_settings
    return settings


def _write_metadata(h5f, config: dict, scope_idn: str, ts_local: str, ts_utc: str,
                    scope_settings: dict):
    """
    Write full metadata structure to HDF5 file matching the expected layout:
      /metadata                  — root attrs (created, idn, project etc.)
      /metadata/bearing          — bearing specs
      /metadata/lubricant        — lubricant specs
      /metadata/scope_settings   — scope hw settings + per-channel subgroups
      /metadata/test_parameters  — test params
    """
    store_cfg  = config.get("store", {}) or {}
    store_attrs = store_cfg.get("attrs", {}) or {}

    meta_grp = h5f.create_group("metadata")
    meta_grp.attrs["created_local"] = ts_local
    meta_grp.attrs["created_utc"]   = ts_utc
    meta_grp.attrs["scope_idn"]     = scope_idn

    # Store-level attrs (project, operator, scope_model …)
    for k, v in store_attrs.items():
        meta_grp.attrs[k] = str(v)

    # --- bearing ---
    bearing_cfg = config.get("bearing", {}) or {}
    bg = meta_grp.create_group("bearing")
    for k, v in bearing_cfg.items():
        try:
            bg.attrs[k] = v
        except Exception:
            bg.attrs[k] = str(v)

    # --- lubricant ---
    lubricant_cfg = config.get("lubricant", {}) or {}
    lg = meta_grp.create_group("lubricant")
    for k, v in lubricant_cfg.items():
        try:
            lg.attrs[k] = v
        except Exception:
            lg.attrs[k] = str(v)

    # --- scope_settings ---
    ss_grp = meta_grp.create_group("scope_settings")
    ch_data = scope_settings.pop("channels", {})
    for k, v in scope_settings.items():
        # Try to cast numerics
        try:
            ss_grp.attrs[k] = float(v)
        except (ValueError, TypeError):
            ss_grp.attrs[k] = str(v) if v is not None else ""

    for ch_alias, ch_vals in ch_data.items():
        cg = ss_grp.create_group(ch_alias)
        for k, v in ch_vals.items():
            try:
                cg.attrs[k] = float(v)
            except (ValueError, TypeError):
                cg.attrs[k] = str(v) if v is not None else ""

    # --- test_parameters ---
    tp_cfg = config.get("test_parameters", {}) or {}
    tpg = meta_grp.create_group("test_parameters")
    for k, v in tp_cfg.items():
        try:
            tpg.attrs[k] = v
        except Exception:
            tpg.attrs[k] = str(v)

    return meta_grp


def acquire_loop(config):
    store_cfg = config["store"]
    acq_cfg   = config["acquisition"]
    channels  = [c for c in config["channels"] if c.get("enabled", True)]

    ts_local, ts_utc = now_pair()
    out_path = store_cfg["output_file"]

    if store_cfg.get("timestamped", True):
        out_path = timestamped_path(out_path, ts_local)

    # Inject scope connection info (used by read_waveform/socket_capture_waveform)
    scope_cfg_inner = {
        "ip": config.get("scope_ip"),
        "scope_ip": config.get("scope_ip"),
        "preferred_port": (config.get("scope", {}) or {}).get("preferred_port", 5025),
    }
    acq_cfg["_scope_cfg"] = scope_cfg_inner

    ip   = scope_cfg_inner["ip"]
    port = int(scope_cfg_inner["preferred_port"])

    # Query IDN and scope settings once before opening HDF5
    scope_idn = ""
    try:
        scope_idn = socket_query_line(ip, port, "*IDN?", timeout_sec=3.0)
    except Exception:
        pass

    scope_settings = {}
    try:
        scope_settings = _query_scope_settings(ip, port, channels)
    except Exception as e:
        if DEBUG:
            print(f"[acquire_loop] Could not query scope settings: {e}")

    # Shared telemetry dict — updated by test_runner via acq_cfg["_telemetry_store"]
    # acquire_loop reads latest value per sweep
    telemetry_store: dict = acq_cfg.get("_telemetry_store") or {}

    def _stop_requested():
        return "stop_event" in acq_cfg and acq_cfg["stop_event"].is_set()

    with h5py.File(out_path, "w") as h5f:
        _write_metadata(h5f, config, scope_idn, ts_local, ts_utc, scope_settings)

        sweeps_grp = h5f.create_group("sweeps")

        samples  = int(acq_cfg["samples"])
        interval = float(acq_cfg["interval_sec"])

        for i in range(samples):

            if _stop_requested():
                print("Stopping acquisition early")
                break

            ts_local, ts_utc = now_pair()
            sweep = sweeps_grp.create_group(f"sweep_{i:03d}")
            sweep.attrs["timestamp_local"] = ts_local
            sweep.attrs["timestamp_utc"]   = ts_utc

            # Write latest telemetry snapshot as sweep attributes
            try:
                telem_snapshot = dict(telemetry_store)
                for k, v in telem_snapshot.items():
                    if v is None:
                        continue
                    try:
                        sweep.attrs[f"telem_{k}"] = v
                    except Exception:
                        sweep.attrs[f"telem_{k}"] = str(v)
            except Exception:
                pass

            # Capture waveforms per channel
            for ch in channels:
                if _stop_requested():
                    print("Stopping acquisition early (between channels)")
                    break

                alias = ch["name"]
                t, v, meta = read_waveform(None, ch, acq_cfg)

                grp = sweep.create_group(alias)
                grp.create_dataset("time",    data=t)
                grp.create_dataset("voltage", data=v)
                for k, val in meta.items():
                    grp.attrs[k] = val

            print(f"[{ts_local}] Sweep {i+1}/{samples}")

            if i < samples - 1:
                if _stop_requested():
                    print("Stopping acquisition early")
                    break
                time.sleep(interval)

    print(f"Gemte data i: {out_path}")
    
def main():
    global DEBUG
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="config.json")
    parser.add_argument("profile", nargs="?", default=None, help="Optional test-profile.json (auto RPM+Temp)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    DEBUG = args.debug

    with open(args.config, "r") as f:
        scope_cfg = json.load(f)

    # --- Manual mode (unchanged) ---
    if not args.profile:
        acquire_loop(scope_cfg)
        return

    # --- Auto mode: runner + scope acquisition paired by run_id ---
    with open(args.profile, "r") as f:
        profile_cfg = json.load(f)

    run_id = make_run_id()

    # Make a run directory next to output_file folder
    out_base = scope_cfg.get("store", {}).get("output_file", "output.h5")
    base_dir = Path(out_base).resolve().parent
    run_dir = base_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stop_event = asyncio.Event()
    scope_stop_event = threading.Event()

    # Shared telemetry dict: test_runner writes latest values, acquire_loop reads per sweep
    # Simple dict — Python GIL makes single-key assignments thread-safe enough here
    telemetry_store: dict = {}

    # Force scope output into run_dir with deterministic name (paired with run_id)
    scope_cfg = _apply_profile_to_scope_cfg(scope_cfg, profile_cfg)
    scope_cfg.setdefault("acquisition", {})
    scope_cfg["acquisition"]["stop_event"] = scope_stop_event
    scope_cfg["acquisition"]["_telemetry_store"] = telemetry_store
    scope_cfg.setdefault("store", {})
    scope_cfg["store"]["timestamped"] = False
    scope_cfg["store"]["output_file"] = str(run_dir / f"scope_{run_id}.h5")

    stop_event = asyncio.Event()
    import signal

    def _handle_signal(signum, frame):
        print(f"[runner] Received signal {signum}, stopping...")
        try:
            stop_event.set()
            scope_stop_event.set()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    scope_err = {"exc": None}

    def scope_thread():
        try:
            acquire_loop(scope_cfg)
        except Exception as e:
            scope_err["exc"] = e
            # stop runner NOW if scope fails
            try:
                # stop_event is in outer scope
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(stop_event.set)
            except Exception:
                # no running loop in this thread; set directly is fine
                stop_event.set()
        finally:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(stop_event.set)
            except Exception:
                pass
                
            scope_done.set()   
            
    scope_done = threading.Event()
    # t = threading.Thread(target=scope_thread, daemon=True)
    t = threading.Thread(target=scope_thread, daemon=False)
    
    t.start()

    async def run_profile():
        # Local imports so manual mode doesn't require these modules
        from test_runner import TestRunner
        from hardware_discovery import discover_serial_ports
        from omron_temp_poll import E5CCTool
        from rs510_vfd_control import RS510VFDController

        rs485_lock = asyncio.Lock()

        runner = TestRunner(
            rs485_lock=rs485_lock,
            data_dir=run_dir,                 # <-- JSONL into same run folder
            discover_serial_ports=discover_serial_ports,
            E5CCTool=E5CCTool,
            RS510VFDController=RS510VFDController,
            run_id=run_id,                    # <-- IMPORTANT: pairs file naming
        )

        def update_cb(msg: dict):
            # Push latest telemetry values into shared store so acquire_loop
            # can stamp each sweep with current RPM, temperature etc.
            for key in ("rpm_target", "rpm_meas", "temp_target",
                        "omron_pv_c", "omron_sv_c",
                        "vfd_cmd_hz", "vfd_frequency_cmd_hz", "vfd_is_running",
                        "mass_g",
                        "elapsed_sec", "current_step", "total_steps"):
                if key in msg:
                    telemetry_store[key] = msg[key]

            # Always print [runner] line so api_server reader thread
            # can update live_telemetry for the UI (not gated on DEBUG)
            try:
                print("[runner]", json.dumps(msg, ensure_ascii=False), flush=True)
            except Exception:
                print("[runner]", msg, flush=True)

        try:
            await runner.run(profile_cfg, update_cb=update_cb, stop_event=stop_event)
        finally:
            stop_event.set()
            scope_stop_event.set()  # Stop scope acquisition when runner finishes

    try:
        asyncio.run(run_profile())
        # Wait for scope to finish all sweeps before exiting (prevents daemon thread from being killed early)
        scope_done.wait()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        t.join(timeout=10.0)

    if scope_err["exc"] is not None:
        raise scope_err["exc"]

    print(f"Run folder: {run_dir}")
    

if __name__ == "__main__":
    main()
