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


# ---------------------------------------------------------------------------
# Unified run event log. Both the scope thread (acquire_loop) and the runner
# side (update_cb / scope-thread exception handler) append here, so ALL
# failures — scope wedges AND RS485/VFD/Modbus errors + the stop reason — land
# in one human-readable file (run_dir/acquire_scope.log).
# ---------------------------------------------------------------------------
_LOG_LOCK = threading.Lock()
_EVENT_LOG_PATH = None  # set once per run by acquire_loop


def _event_log(msg):
    line = f"[{now_pair()[0]}] {msg}"
    print(line, flush=True)
    p = _EVENT_LOG_PATH
    if not p:
        return
    try:
        with _LOG_LOCK:
            with open(p, "a", encoding="utf-8") as lf:
                lf.write(line + "\n")
    except Exception:
        pass


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

def socket_capture_waveform(ip: str, port: int, src: str, points: int, fmt: str, timeout_sec: float = 15.0,
                            points_mode: str = "RAW"):
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

        # Digitize first — acquire into full memory
        send(s, ":DIGITIZE")
        query_opc(s)

        # Configure waveform readout AFTER acquisition
        send(s, f":WAV:SOUR {src}")
        send(s, f":WAV:POIN:MODE {points_mode}")
        send(s, f":WAV:POIN {points}")
        send(s, f":WAV:FORM {fmt}")

        if fmt == "WORD":
            send(s, ":WAV:UNS 0")
            send(s, ":WAV:BYT MSBFirst")
        else:
            send(s, ":WAV:UNS 1")

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


# ---------------------------------------------------------------------------
# Shared low-level SCPI socket helpers (used by socket_capture_sweep).
# Mirror the proven logic from socket_capture_waveform(), but at module level
# so a SINGLE TCP session + a SINGLE :DIGITIZE can serve a whole multi-channel
# sweep instead of digitizing once per channel.
# ---------------------------------------------------------------------------
def _scpi_send(s, cmd):
    s.sendall((cmd + "\n").encode("ascii", errors="ignore"))


def _scpi_recv_first_then_drain(s, first_timeout, drain_timeout=0.2):
    s.settimeout(first_timeout)
    first = s.recv(4096)
    if not first:
        return b""
    chunks = [first]
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


def _scpi_query_text(s, cmd, timeout_sec):
    _scpi_send(s, cmd)
    data = _scpi_recv_first_then_drain(s, first_timeout=timeout_sec, drain_timeout=0.2)
    return data.decode(errors="ignore").strip()


def _scpi_recv_exact(s, n):
    chunks = []
    remaining = n
    while remaining > 0:
        buf = s.recv(min(65536, remaining))
        if not buf:
            raise ConnectionError("Socket closed during recv_exact")
        chunks.append(buf)
        remaining -= len(buf)
    return b"".join(chunks)


def _scpi_query_ieee_block(s, cmd, timeout_sec):
    """Send a query returning an IEEE 488.2 definite-length block; return payload."""
    _scpi_send(s, cmd)
    s.settimeout(timeout_sec)
    first2 = _scpi_recv_exact(s, 2)
    if not first2.startswith(b"#"):
        rest = _scpi_recv_first_then_drain(s, first_timeout=0.5, drain_timeout=0.2)
        return first2 + rest
    nd = int(chr(first2[1]))
    len_bytes = _scpi_recv_exact(s, nd)
    nlen = int(len_bytes.decode("ascii"))
    payload = _scpi_recv_exact(s, nlen)
    try:
        s.settimeout(0.2)
        _ = s.recv(2)
    except Exception:
        pass
    return payload


def socket_capture_sweep(ip, port, sources, points, fmt, timeout_sec=30.0, points_mode="RAW"):
    """
    Capture every channel from a SINGLE acquisition: one :DIGITIZE, then read
    each source from the same acquisition memory over one reused TCP connection.

    This is ~Nx lighter on the scope than digitizing per channel (one digitize
    and one socket instead of N), and all channels come from the same shot.

    Returns: { source: (raw_ndarray, xinc, xorg, xref, yinc, yorg, yref), ... }
    Raises on protocol/transport failure so the caller can retry/skip the sweep.
    """
    import socket
    import numpy as np

    step = "connect"
    s = None
    try:
        s = socket.create_connection((ip, port), timeout=timeout_sec)
        s.settimeout(timeout_sec)

        # Fresh state, then ONE digitize for all displayed channels
        step = "*CLS"
        _scpi_send(s, "*CLS")
        _scpi_query_text(s, "*OPC?", timeout_sec)
        step = "DIGITIZE"
        _scpi_send(s, ":DIGITIZE")
        step = "OPC-after-DIGITIZE"
        _scpi_query_text(s, "*OPC?", timeout_sec)

        # Readout format — set once for the connection (persists across sources)
        step = "config-readout"
        _scpi_send(s, f":WAV:POIN:MODE {points_mode}")
        _scpi_send(s, f":WAV:POIN {points}")
        _scpi_send(s, f":WAV:FORM {fmt}")
        if fmt == "WORD":
            _scpi_send(s, ":WAV:UNS 0")
            _scpi_send(s, ":WAV:BYT MSBFirst")
        else:
            _scpi_send(s, ":WAV:UNS 1")

        results = {}
        for src in sources:
            step = f"SOUR {src}"
            _scpi_send(s, f":WAV:SOUR {src}")

            # Preamble is per-channel (vertical scale differs)
            step = f"PRE? {src}"
            pre_line = _scpi_query_text(s, ":WAV:PRE?", timeout_sec)
            if not pre_line:
                err = _scpi_query_text(s, ":SYST:ERR?", timeout_sec)
                raise RuntimeError(f"Empty PRE? for {src}. SYST:ERR?={err}")
            pre = pre_line.split(",")
            xinc = float(pre[4]); xorg = float(pre[5]); xref = float(pre[6])
            yinc = float(pre[7]); yorg = float(pre[8]); yref = float(pre[9])

            step = f"DATA? {src}"
            payload = _scpi_query_ieee_block(s, ":WAV:DATA?", timeout_sec)
            if fmt == "WORD":
                raw = np.frombuffer(payload, dtype=">i2")
            else:
                raw = np.frombuffer(payload, dtype=np.uint8)

            results[src] = (raw, xinc, xorg, xref, yinc, yorg, yref)

        return results
    except Exception as e:
        # Annotate which SCPI step failed so the caller's log pinpoints the cause
        raise RuntimeError(f"step={step}: {type(e).__name__}: {e}") from e
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def _raw_to_tv(raw, pre, src):
    """Convert raw samples + preamble (xinc,xorg,xref,yinc,yorg,yref) to (t, v, meta)."""
    xinc, xorg, xref, yinc, yorg, yref = pre
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


def read_waveform(scope, channel_cfg, acq_cfg):
    src = channel_cfg["source"]
    pts_cfg = acq_cfg["points"]
    points = "MAX" if str(pts_cfg).upper() == "MAX" else int(pts_cfg)
    fmt = acq_cfg.get("waveform_format", "WORD").upper()
    points_mode = str(acq_cfg.get("points_mode", "RAW")).upper()

    scope_cfg = acq_cfg.get("_scope_cfg") or {}
    ip = scope_cfg.get("ip") or scope_cfg.get("scope_ip")
    port = int(scope_cfg.get("preferred_port", 5025))

    # socket-only capture (UI-sekvens på én TCP session)
    raw, xinc, xorg, xref, yinc, yorg, yref = socket_capture_waveform(
        ip=ip, port=port, src=src, points=points, fmt=fmt, timeout_sec=15.0,
        points_mode=points_mode
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
        sp = prof_acq["scope_points"]
        out["acquisition"]["points"] = "MAX" if str(sp).upper() == "MAX" else int(sp)

    if "waveform_format" in prof_acq and prof_acq["waveform_format"]:
        out["acquisition"]["waveform_format"] = str(prof_acq["waveform_format"])

    # Acquisition setup: a profile overrides config.json ONLY for the keys it
    # actually specifies. Keys absent from the profile keep the config.json
    # default (deep-copied into `out` at the top of this function).
    for key in ("points_mode", "acq_type", "trigger_sweep"):
        if prof_acq.get(key):
            out["acquisition"][key] = str(prof_acq[key])

    # acq_points (acquisition memory depth) may be an int or "MAX"
    if prof_acq.get("acq_points") is not None:
        out["acquisition"]["acq_points"] = prof_acq["acq_points"]

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


def _scope_write(ip: str, port: int, cmd: str, timeout_sec: float = 3.0):
    """Send a write-only SCPI command (no response expected)."""
    import socket as _socket
    s = _socket.create_connection((ip, port), timeout=timeout_sec)
    s.settimeout(timeout_sec)
    try:
        if not cmd.endswith("\n"):
            cmd += "\n"
        s.sendall(cmd.encode("ascii", errors="ignore"))
        time.sleep(0.05)  # brief pause for scope to process
    finally:
        try:
            s.close()
        except Exception:
            pass


def _apply_scope_channel_settings(ip: str, port: int, channels: list, profile_cfg: dict):
    """
    Apply scope channel settings from test profile scope_channels section.
    Only channels listed in scope_channels are adjusted.
    """
    scope_ch_cfg = (profile_cfg or {}).get("scope_channels", {})
    if not scope_ch_cfg:
        return

    name_to_source = {ch["name"]: ch["source"] for ch in channels}

    for alias, settings in scope_ch_cfg.items():
        src = name_to_source.get(alias)
        if not src:
            if DEBUG:
                print(f"[scope_channels] Unknown alias '{alias}', skipping")
            continue
        try:
            if "timebase_range" in settings:
                _scope_write(ip, port, f":TIM:RANG {settings['timebase_range']}")
            if "volt_range" in settings:
                _scope_write(ip, port, f":{src}:RANG {settings['volt_range']}")
            if "volt_offset" in settings:
                _scope_write(ip, port, f":{src}:OFFS {settings['volt_offset']}")
            if "coupling" in settings:
                _scope_write(ip, port, f":{src}:COUP {settings['coupling']}")
            if DEBUG:
                print(f"[scope_channels] Applied {alias} ({src}): {settings}")
        except Exception as e:
            if DEBUG:
                print(f"[scope_channels] Error applying {alias}: {e}")


def _apply_scope_acquisition_settings(ip: str, port: int, acq_cfg: dict):
    """
    Apply global acquisition settings to the scope from the resolved config.

    These affect HOW :DIGITIZE acquires, so they must be set before acquisition:
      - acq_type      -> :ACQ:TYPE   (NORM | AVER | HRES | PEAK)
      - trigger_sweep -> :TRIG:SWE   (AUTO | NORM)
      - acq_points    -> :ACQ:POIN   (acquisition memory depth; int or "MAX")

    Memory depth is the lever for "max points per channel": in a fixed time
    window, points_captured = sample_rate * timebase_range, capped by the memory
    depth. Left on auto the scope picks a modest depth; forcing it up raises the
    sample rate (and the data captured) for the same time/div.

    points_mode / waveform_format / points are waveform *readout* settings and
    are applied per-capture in socket_capture_waveform(), not here.

    Precedence is already resolved upstream (profile overrides config.json in
    _apply_profile_to_scope_cfg); in manual mode acq_cfg is config.json directly.
    """
    if not acq_cfg:
        return

    acq_type      = acq_cfg.get("acq_type")
    trigger_sweep = acq_cfg.get("trigger_sweep")
    acq_points    = acq_cfg.get("acq_points")

    try:
        if acq_type:
            _scope_write(ip, port, f":ACQ:TYPE {str(acq_type).upper()}")
        if trigger_sweep:
            _scope_write(ip, port, f":TRIG:SWE {str(trigger_sweep).upper()}")
        if acq_points:
            # A number is clamped by the scope to its max valid depth for the
            # active-channel count; "MAX" is accepted on some firmware. If the
            # scope rejects the value it simply stays on auto (no crash).
            _scope_write(ip, port, f":ACQ:POIN {str(acq_points).upper()}")
        if DEBUG:
            print(f"[scope_acq] Applied acq_type={acq_type}, trigger_sweep={trigger_sweep}, acq_points={acq_points}")
    except Exception as e:
        if DEBUG:
            print(f"[scope_acq] Error applying acquisition settings: {e}")


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

    # --- HDF5 compression settings from store config ---
    # Supported: "none", "gzip", "lzf"
    # gzip accepts compression_opts 1-9 (default 4)
    compress_mode = str(store_cfg.get("compress", "none")).strip().lower()
    ds_kwargs = {}  # extra kwargs for create_dataset()

    if compress_mode in ("gzip", "lzf"):
        ds_kwargs["compression"] = compress_mode
        ds_kwargs["chunks"] = True  # required for compression
        if compress_mode == "gzip":
            ds_kwargs["compression_opts"] = int(store_cfg.get("compression_level", 4))
        if DEBUG:
            print(f"[acquire_loop] HDF5 compression: {compress_mode} (opts={ds_kwargs.get('compression_opts', 'N/A')})")
    elif store_cfg.get("chunk", False):
        # Chunking without compression (allows resizing etc.)
        ds_kwargs["chunks"] = True
    if DEBUG and not ds_kwargs:
        print("[acquire_loop] HDF5 compression: none")

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

    # Small delay to let scope finish IDN response before sending channel settings
    time.sleep(0.5)

    # Apply profile scope_channels FIRST, then query so HDF5 reflects actual settings
    try:
        _apply_scope_channel_settings(ip, port, channels, config.get("_profile_cfg"))
    except Exception as e:
        if DEBUG:
            print(f"[acquire_loop] Could not apply scope channel settings: {e}")

    # Apply global acquisition settings (acq_type, trigger_sweep) from the
    # resolved config so they take effect on the scope AND so the settings
    # queried below for HDF5 metadata reflect the configured values.
    try:
        _apply_scope_acquisition_settings(ip, port, acq_cfg)
    except Exception as e:
        if DEBUG:
            print(f"[acquire_loop] Could not apply scope acquisition settings: {e}")

    # Wait for scope to process settings before querying
    time.sleep(0.5)

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

        # Record compression settings in file metadata
        h5f.attrs["compression"] = compress_mode
        if compress_mode == "gzip":
            h5f.attrs["compression_level"] = ds_kwargs.get("compression_opts", 4)

        sweeps_grp = h5f.create_group("sweeps")

        samples  = int(acq_cfg["samples"])
        interval = float(acq_cfg["interval_sec"])

        # --- Capture parameters (resolved once) ---
        pts_cfg = acq_cfg["points"]
        cap_points = "MAX" if str(pts_cfg).upper() == "MAX" else int(pts_cfg)
        cap_fmt = acq_cfg.get("waveform_format", "WORD").upper()
        cap_points_mode = str(acq_cfg.get("points_mode", "RAW")).upper()
        cap_timeout = float(acq_cfg.get("read_timeout_sec", 30.0))
        max_retries = int(acq_cfg.get("sweep_retries", 2))
        cap_channels = [(ch["name"], ch["source"]) for ch in channels]
        cap_sources = [src for (_a, src) in cap_channels]

        # Unified per-run event log shared with the runner side (see _event_log):
        # scope failures AND RS485/VFD/Modbus errors + stop reason land together.
        global _EVENT_LOG_PATH
        _EVENT_LOG_PATH = str(Path(out_path).parent / "acquire_scope.log")
        _logr = _event_log

        def _recover_scope():
            # Un-wedge a stuck scope WITHOUT losing setup: :STOP halts acquisition
            # and *CLS clears status/errors — NEITHER changes timebase, volt/div,
            # memory depth or trigger. Then re-assert our settings so the retry is
            # guaranteed to capture at the intended config even if the scope state
            # was disturbed (NOT *RST / :SYST:PRES — those would reset to factory).
            try:
                import socket as _sock
                rs = _sock.create_connection((ip, port), timeout=5.0)
                rs.settimeout(5.0)
                try:
                    rs.sendall(b":STOP\n")
                    rs.sendall(b"*CLS\n")
                finally:
                    rs.close()
            except Exception as e:
                _logr(f"  recover: STOP/*CLS failed: {e!r}")
            try:
                _apply_scope_channel_settings(ip, port, channels, config.get("_profile_cfg"))
                _apply_scope_acquisition_settings(ip, port, acq_cfg)
            except Exception as e:
                _logr(f"  recover: re-apply settings failed: {e!r}")

        _logr(f"acquire start: {len(cap_sources)} ch {cap_sources} points={cap_points} "
              f"fmt={cap_fmt} mode={cap_points_mode} timeout={cap_timeout}s retries={max_retries}")

        skipped = 0

        for i in range(samples):

            if _stop_requested():
                _logr("Stopping acquisition early (stop_event set)")
                break

            sweep_t0 = time.monotonic()
            ts_local, ts_utc = now_pair()

            # --- Capture ALL channels in ONE acquisition (retry; skip on fail) ---
            # One :DIGITIZE + one reused TCP connection for every channel: far
            # lighter on the scope than digitizing per channel, and a transient
            # failure now costs a single sweep instead of aborting the whole run.
            captured = None
            for attempt in range(1, max_retries + 2):
                if _stop_requested():
                    break
                try:
                    captured = socket_capture_sweep(
                        ip, port, cap_sources, cap_points, cap_fmt,
                        timeout_sec=cap_timeout, points_mode=cap_points_mode,
                    )
                    break
                except Exception as e:
                    _logr(f"[sweep {i+1}/{samples}] capture attempt {attempt} failed: {e!r}")
                    if attempt <= max_retries:
                        _logr(f"[sweep {i+1}/{samples}] resetting scope before retry")
                        _recover_scope()
                    time.sleep(0.5)

            if captured is None:
                if _stop_requested():
                    _logr("Stopping acquisition early (stop_event set)")
                    break
                skipped += 1
                _logr(f"[sweep {i+1}/{samples}] SKIPPED (capture failed); continuing run")
                if i < samples - 1:
                    time.sleep(interval)
                continue

            # --- Write sweep ---
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

            for alias, src in cap_channels:
                tup = captured.get(src)
                if tup is None:
                    continue
                raw = tup[0]
                pre = tup[1:7]
                t, v, meta = _raw_to_tv(raw, pre, src)
                grp = sweep.create_group(alias)
                grp.create_dataset("time",    data=t, **ds_kwargs)
                grp.create_dataset("voltage", data=v, **ds_kwargs)
                for k, val in meta.items():
                    grp.attrs[k] = val

            _msg = f"Sweep {i+1}/{samples}" + (f"  (skipped: {skipped})" if skipped else "")
            if (i + 1) % 25 == 0:
                _logr(_msg)                       # periodic checkpoint in the persistent log
            else:
                print(f"[{ts_local}] {_msg}", flush=True)

            if i < samples - 1:
                if _stop_requested():
                    _logr("Stopping acquisition early (stop_event set)")
                    break
                # interval_sec is the sweep *period*, not an extra gap after the work.
                # Sleeping the full interval made the real cadence (work + interval),
                # so `samples` (= duration/interval) was never reachable and the
                # reported sweep_total always overstated what the run could do.
                time.sleep(max(0.0, interval - (time.monotonic() - sweep_t0)))

        _logr(f"acquire loop ended — {skipped} sweep(s) skipped")

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
    scope_cfg["_profile_cfg"] = profile_cfg  # for scope_channels settings
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
            try:
                import traceback
                _event_log(f"[scope] FATAL: {e!r}\n{traceback.format_exc()}")
            except Exception:
                pass
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

        _runner_seen = {"stop": None, "err": None}

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

            # Surface RS485/VFD/runner errors + the stop reason into the shared
            # event log so failures are human-readable in acquire_scope.log
            # (not just buried per-sample in the telemetry JSONL).
            try:
                sr = msg.get("stop_reason")
                if sr and sr != _runner_seen["stop"]:
                    _runner_seen["stop"] = sr
                    _event_log(f"[runner] STOP reason={sr}")
                err = (msg.get("vfd_error") or msg.get("rpm_read_error")
                       or msg.get("omron_error") or msg.get("modbus_error"))
                if err and err != _runner_seen["err"]:
                    _runner_seen["err"] = err
                    _event_log(f"[runner] comm error: {err}")
            except Exception:
                pass

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