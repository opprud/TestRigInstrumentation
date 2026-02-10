#!/usr/bin/env python3
"""
FastAPI server to bridge Python hardware tools with React frontend.

Provides REST API endpoints for:
- Hardware discovery and status
- RP2040 communication
- Configuration management
- Test control

Run with: uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our hardware discovery functions
#from hardware_discovery import discover_hardware
from hardware_discovery import discover_hardware, discover_serial_ports
from omron_temp_poll import E5CCTool
from rs510_vfd_control import RS510VFDController, VFDCommand, VFDState

from test_runner import TestRunner
import asyncio
from pathlib import Path
from shared_modbus_manager import reset_shared_modbus_manager


# --- Global locks ---
_rs485_lock = asyncio.Lock()

app = FastAPI(
    title="Test Rig API",
    description="Backend API for Test Rig Instrumentation Dashboard",
    version="1.0.0"
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
class HardwareStatus(BaseModel):
    timestamp: str
    scope: Dict
    rp2040: Dict
    rs485: Dict
    ports: Dict

class RP2040Command(BaseModel):
    command: str
    port: Optional[str] = None

class TestConfig(BaseModel):
    name: str
    description: str
    duration_minutes: int
    setpoints: Dict
    acquisition: Dict

class OmronCommand(BaseModel):
    action: str  # 'read_pv', 'read_sv', 'write_sv'
    value: Optional[float] = None  # For write_sv
    port: Optional[str] = None

class VFDCommand(BaseModel):
    action: str  # 'status', 'start_forward', 'start_reverse', 'stop', 'emergency_stop', 'set_frequency'
    frequency_hz: Optional[float] = None  # For set_frequency and start commands
    port: Optional[str] = None
    slave_id: Optional[int] = 1

class VFDStatusResponse(BaseModel):
    frequency_hz: float
    frequency_command_hz: float
    run_command: str
    status: str
    output_current_a: float
    dc_bus_voltage_v: float
    fault_code: int
    temperature_c: float
    is_running: bool
    is_fault: bool
    timestamp: str

# --- Global State ---
_last_hardware_scan = None
_hardware_cache_duration = 30  # seconds

# Global lock for oscilloscope access to prevent concurrent SCPI commands
_scope_lock = threading.Lock()

import os
import time
import time
from collections import deque

_runner_task = None
_runner_stop = None



# --- Run logging (JSONL) ---
_log_task: Optional[asyncio.Task] = None
_log_path: Optional[Path] = None

def _log_runs_dir() -> Path:
    """Directory for per-run JSONL logs (py/data/runs)."""
    d = Path(__file__).parent / "data" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d

async def _log_loop(sample_period_sec: float):
    """Background logger that appends JSONL rows to the current run log.

    It **does not** open RS485 itself; it just snapshots the last-known values
    already produced by your existing polling endpoints (Omron/VFD/RP2040/etc.).
    This keeps behavior unchanged and avoids reintroducing Errno 11.
    """
    global _log_path

    if not _log_path:
        return

    # Write an initial header row (metadata)
    try:
        meta = {
            "type": "run_start",
            "ts": datetime.now().isoformat(),
            "profile": _run_state.get("profile_name"),
            "duration_sec": _run_state.get("duration_sec"),
            "total_steps": _run_state.get("total_steps"),
        }
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    except Exception:
        pass

    while True:
        # Stop conditions
        if _run_state.get("state") != "running":
            break
        if _runner_stop is not None:
            try:
                if hasattr(_runner_stop, "is_set") and _runner_stop.is_set():
                    break
            except Exception:
                pass

        # Update elapsed from started_at (same logic as /api/run/status)
        try:
            if _run_state.get("started_at"):
                start_dt = datetime.fromisoformat(_run_state["started_at"])
                _run_state["elapsed_sec"] = max(0.0, (datetime.now() - start_dt).total_seconds())
        except Exception:
            pass

        row = {
            "type": "sample",
            "ts": datetime.now().isoformat(),
            "run": {
                "elapsed_sec": _run_state.get("elapsed_sec"),
                "current_step": _run_state.get("current_step"),
                "total_steps": _run_state.get("total_steps"),
                "duration_sec": _run_state.get("duration_sec"),
                "state": _run_state.get("state"),
            },
            "omron": dict(_omron_last_good) if isinstance(_omron_last_good, dict) else {},
            "vfd": dict(_vfd_last_good) if isinstance(_vfd_last_good, dict) else {},
        }

        try:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            # If we cannot write, don't kill the run; just stop logging
            break

        await asyncio.sleep(max(0.05, float(sample_period_sec)))

    # Final row
    try:
        tail = {
            "type": "run_end",
            "ts": datetime.now().isoformat(),
            "state": _run_state.get("state"),
            "error": _run_state.get("error"),
        }
        if _log_path:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(tail, ensure_ascii=False) + "\n")
    except Exception:
        pass
# live “tick” data til frontend
_live_ticks = deque(maxlen=5000)  # gem de seneste N samples

_run_task: asyncio.Task | None = None
_run_stop_event = asyncio.Event()

def _runs_dir() -> Path:
    d = Path(__file__).parent / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _now_iso() -> str:
    return datetime.now().isoformat()

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

# --- Simple Run State (minimal) ---
_run_state = {
    "state": "idle",          # idle | running | stopped
    "started_at": None,       # ISO timestamp string
    "elapsed_sec": 0.0,
    "duration_sec": 0,
    "current_step": 0,
    "total_steps": 0,
    "profile_name": None,
    "error": None,
}

# --- Last-known caches to avoid RS485 re-open storms (Errno 11) ---
_omron_last_good: Dict[str, Any] = {}
_vfd_last_good: Dict[str, Any] = {}


def _is_resource_busy_exc(e: Exception) -> bool:
    s = str(e)
    return ("Errno 11" in s) or ("Resource temporarily unavailable" in s) or ("exclusively lock port" in s)


_runner_task: Optional[asyncio.Task] = None
_runner_stop: Optional[asyncio.Event] = None

# --- API Endpoints ---

@app.get("/api/run/ticks")
async def run_ticks(interval_sec: float):
    global _runner_stop

    try:
        # Guard
        if _run_state.get("total_steps", 0) <= 0:
            _run_state.update({
                "state": "stopped",
                "error": "total_steps=0 (check duration_minutes/acquisition settings)"
            })
            return

        # Kør step for step
        while True:
            if _runner_stop and _runner_stop.is_set():
                _run_state.update({"state": "stopped"})
                return

            # Stop når vi har ramt slut
            if _run_state["current_step"] >= _run_state["total_steps"]:
                _run_state.update({"state": "stopped"})
                return

            # Vent et tick
            await asyncio.sleep(max(0.05, float(interval_sec)))

            # Increment step
            _run_state["current_step"] += 1

    except Exception as e:
        _run_state.update({"state": "stopped", "error": f"runner exception: {e}"})
        return
        
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Test Rig Instrumentation API",
        "version": "1.0.0",
        "endpoints": {
            "hardware": "/api/hardware/discover",
            "rp2040": "/api/rp2040/command",
            "config": "/api/config",
            "health": "/api/health"
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "python_backend": "running"
    }

@app.get("/api/hardware/discover", response_model=HardwareStatus)
async def discover_hardware_api(force_scan: bool = False):
    """
    SAFE discovery endpoint:
    - Never opens RS485 (never calls discover_hardware()).
    - Returns ports-only info suitable for frontend polling.
    - Uses cache unless force_scan=True.
    """
    global _last_hardware_scan

    try:
        # Use cached results if recent and not forcing scan
        if (not force_scan and
            _last_hardware_scan and
            (datetime.now() - _last_hardware_scan['timestamp']).total_seconds() < _hardware_cache_duration):
            return _last_hardware_scan['data']

        # Ports-only discovery (safe: does not open /dev/ttyUSB0)
        ports = discover_serial_ports()

        hardware_info = {
            "timestamp": datetime.now().isoformat(),
            "scope": {"status": "unknown"},
            "rp2040": {"status": "unknown"},
            "rs485": {"status": "unknown"},
            "ports": ports,
        }

        _last_hardware_scan = {"timestamp": datetime.now(), "data": hardware_info}
        return hardware_info

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hardware discovery failed: {str(e)}")

@app.post("/api/rp2040/command")
async def send_rp2040_command(command: RP2040Command):
    """
    Send command to RP2040 device.
    
    Supports commands: PING, INFO, LOAD?, SPEED?, TARE, etc.
    """
    try:
        import serial
        import time
        
        # Find RP2040 port if not specified
        ports = discover_serial_ports()
        rp_ports = ports.get("rp2040", [])
        if not rp_ports:
            raise HTTPException(status_code=404, detail="No RP2040 device found")
        port = rp_ports[0]["device"]

        # Send command
        with serial.Serial(port, 115200, timeout=2.0) as ser:
            ser.write(f'{command.command}\r\n'.encode())
            time.sleep(0.1)
            
            response = ser.readline().decode('ascii', errors='ignore').strip()
            
            return {
                "command": command.command,
                "port": port,
                "response": response,
                "timestamp": datetime.now().isoformat(),
                "success": response.startswith('OK')
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RP2040 communication failed: {str(e)}")

@app.get("/api/rp2040/status")
async def get_rp2040_status():
    """Get RP2040 status + sensor readings (LOAD?/SPEED?) without calling discover_hardware()."""
    try:
        ports = discover_serial_ports()
        rp_ports = ports.get("rp2040", [])

        if not rp_ports:
            return {
                "status": "no_device",
                "error": "No RP2040 device found",
                "timestamp": datetime.now().isoformat()
            }

        port = rp_ports[0].get("device")
        if not port:
            return {
                "status": "error",
                "error": "RP2040 port entry missing 'device'",
                "timestamp": datetime.now().isoformat()
            }

        import serial
        import time

        with serial.Serial(port, 115200, timeout=2.0) as ser:
            ser.write(b"LOAD?\r\n")
            time.sleep(0.1)
            load_response = ser.readline().decode("ascii", errors="ignore").strip()

            ser.write(b"SPEED?\r\n")
            time.sleep(0.1)
            speed_response = ser.readline().decode("ascii", errors="ignore").strip()

        return {
            "status": "connected",
            "port": port,
            "timestamp": datetime.now().isoformat(),
            "load_reading": load_response,
            "speed_reading": speed_response
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/config/profiles")
async def list_config_profiles():
    """List available test configuration profiles."""
    try:
        config_dir = Path(__file__).parent.parent / "react" / "public" / "config"
        profiles = []
        
        if config_dir.exists():
            for config_file in config_dir.glob("*.json"):
                try:
                    with open(config_file) as f:
                        config_data = json.load(f)
                    
                    profiles.append({
                        "filename": config_file.name,
                        "path": f"/config/{config_file.name}",
                        "name": config_data.get("name", config_file.stem),
                        "description": config_data.get("description", ""),
                        "duration_minutes": config_data.get("duration_minutes", 0)
                    })
                except Exception as e:
                    print(f"Error reading {config_file}: {e}")
                    
        return {"profiles": profiles}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list profiles: {str(e)}")

@app.get("/api/system/ports")
async def list_system_ports():
    """List all available serial ports on the system."""
    try:
        import serial.tools.list_ports
        
        ports = []
        for port in serial.tools.list_ports.comports():
            port_info = {
                'device': port.device,
                'description': port.description,
                'hwid': port.hwid,
                'vid': f"{port.vid:04X}" if port.vid else None,
                'pid': f"{port.pid:04X}" if port.pid else None,
                'serial_number': port.serial_number,
                'manufacturer': port.manufacturer,
                'product': port.product,
            }
            
            # Add device type detection
            if port.vid and port.pid:
                if port.vid == 0x2E8A and port.pid == 0x0005:
                    port_info['device_type'] = 'Raspberry Pi Pico (RP2040)'
                elif port.vid == 0x2886 and port.pid == 0x8027:
                    port_info['device_type'] = 'Seeed Studio XIAO RP2040'
                elif port.vid == 0x0403:
                    port_info['device_type'] = 'FTDI USB-Serial'
                else:
                    port_info['device_type'] = 'Unknown'
            
            ports.append(port_info)
        
        return {"ports": ports, "count": len(ports)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list ports: {str(e)}")

@app.get("/api/run/status")
async def run_status():
    """Return current run status for frontend (Step x/y + elapsed)."""
    if _run_state["state"] == "running" and _run_state["started_at"]:
        try:
            start_dt = datetime.fromisoformat(_run_state["started_at"])
            _run_state["elapsed_sec"] = max(0.0, (datetime.now() - start_dt).total_seconds())
        except Exception:
            pass

        # Minimal step counter based on elapsed time
        if _run_state["duration_sec"] > 0 and _run_state["total_steps"] > 0:
            progress = min(1.0, _run_state["elapsed_sec"] / float(_run_state["duration_sec"]))
            _run_state["current_step"] = max(
                1,
                min(_run_state["total_steps"], int(progress * _run_state["total_steps"]) + 1)
            )

    return _run_state

async def _run_sequence(cfg: Dict):
    """
    Minimal backend runner:
    - loops each interval_sec
    - reads sensors (best-effort)
    - logs JSONL
    - updates _run_state
    """
    duration_min = (
        cfg.get("duration_minutes")
        or (cfg.get("test_parameters", {}) or {}).get("duration_minutes")
        or 0
    )
    duration_sec = int(float(duration_min) * 60)

    acq = cfg.get("acquisition", {}) or {}
    interval_sec = float(acq.get("interval_sec") or 1.0)
    samples_per_step = int(acq.get("samples_per_step") or 1)
    if interval_sec <= 0:
        interval_sec = 1.0
    samples_per_step = max(1, samples_per_step)

    profile_name = cfg.get("name") or "run"
    started_at = datetime.fromisoformat(_run_state["started_at"]) if _run_state["started_at"] else datetime.now()

    # log file
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _runs_dir() / f"{stamp}_{profile_name.replace(' ', '_')}.jsonl"

    # helper: best-effort reads
    async def read_omron():
        # bruger samme logik som dit endpoint, men uden HTTP-kald
        async with _rs485_lock:
            ports = discover_serial_ports()
            ftdi_ports = ports.get("ftdi", [])
            if not ftdi_ports:
                return {"status": "no_device"}
            port = ftdi_ports[0]["device"]
            tool = E5CCTool(
                port=port, baudrate=9600, parity="N", bytesize=8, stopbits=1,
                timeout=2.0, unit_id=2, pv_address=0x2000, sv_address=0x2103,
                scale=1.0, debug=False
            )
            try:
                pv = tool.read_pv_c()
                sv = tool.read_sv_c()
                return {"status": "connected", "port": port, "pv": pv, "sv": sv}
            finally:
                tool.close()

    async def read_vfd():
        async with _rs485_lock:
            ports = discover_serial_ports()
            ftdi_ports = ports.get("ftdi", [])
            if not ftdi_ports:
                return {"status": "no_device"}
            port = ftdi_ports[0]["device"]
            vfd = RS510VFDController(port=port, slave_id=3, baudrate=9600, timeout=2.0, debug=False)
            if not vfd.connect():
                return {"status": "connection_failed", "port": port}
            try:
                s = vfd.get_status()
                return {
                    "status": "connected",
                    "port": port,
                    "hz": s.frequency_hz,
                    "hz_cmd": s.frequency_command_hz,
                    "run": getattr(s.run_command, "name", str(s.run_command)),
                    "state": getattr(s.status, "name", str(s.status)),
                    "i_a": s.output_current_a,
                    "dc_v": s.dc_bus_voltage_v,
                    "fault": s.fault_code,
                    "temp_c": s.temperature_c,
                    "is_running": s.is_running,
                    "is_fault": s.is_fault,
                }
            finally:
                vfd.disconnect()

    async def read_rp2040():
        ports = discover_serial_ports()
        rp_ports = ports.get("rp2040", [])
        if not rp_ports:
            return {"status": "no_device"}
        port = rp_ports[0].get("device")
        if not port:
            return {"status": "error", "error": "missing device key"}
        try:
            import serial
            with serial.Serial(port, 115200, timeout=2.0) as ser:
                ser.write(b"LOAD?\r\n")
                await asyncio.sleep(0.1)
                load = ser.readline().decode("ascii", errors="ignore").strip()

                ser.write(b"SPEED?\r\n")
                await asyncio.sleep(0.1)
                speed = ser.readline().decode("ascii", errors="ignore").strip()

            return {"status": "connected", "port": port, "load": load, "speed": speed}
        except Exception as e:
            return {"status": "error", "error": str(e), "port": port}

    # loop
    _run_stop_event.clear()
    step = 0
    total_steps = _run_state.get("total_steps", 0) or 0

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "run_start", "ts": _now_iso(), "profile": profile_name, "cfg": cfg}) + "\n")
        f.flush()

        try:
            while True:
                if _run_stop_event.is_set():
                    break

                elapsed = (datetime.now() - started_at).total_seconds()
                _run_state["elapsed_sec"] = float(max(0.0, elapsed))

                # stop on duration
                if duration_sec > 0 and elapsed >= duration_sec:
                    break

                # sample(s) per interval
                for _ in range(samples_per_step):
                    if _run_stop_event.is_set():
                        break

                    step += 1
                    _run_state["current_step"] = step
                    if total_steps > 0:
                        _run_state["total_steps"] = total_steps

                    sample = {
                        "type": "sample",
                        "ts": _now_iso(),
                        "elapsed_sec": _run_state["elapsed_sec"],
                        "step": step,
                        "profile": profile_name,
                        "omron": await read_omron(),
                        "vfd": await read_vfd(),
                        "rp2040": await read_rp2040(),
                    }

                    f.write(json.dumps(sample) + "\n")
                    f.flush()

                await asyncio.sleep(interval_sec)

        except asyncio.CancelledError:
            f.write(json.dumps({"type": "run_cancelled", "ts": _now_iso()}) + "\n")
            f.flush()
            raise
        except Exception as e:
            _run_state["error"] = str(e)
            f.write(json.dumps({"type": "run_error", "ts": _now_iso(), "error": str(e)}) + "\n")
            f.flush()
        finally:
            f.write(json.dumps({"type": "run_end", "ts": _now_iso()}) + "\n")
            f.flush()

async def _run_loop(cfg: dict, stop_event: asyncio.Event):
    """
    Minimal runner:
    - kører i realtid indtil duration er nået eller stop_event sættes
    - opdaterer _run_state og _live_ticks så frontend kan tegne playhead og evt. data
    """
    started = time.time()

    duration_min = float(cfg.get("duration_minutes") or 0)
    duration_sec = max(0.0, duration_min * 60.0)

    acq = cfg.get("acquisition", {}) or {}
    interval_sec = float(acq.get("interval_sec") or 1.0)
    interval_sec = max(0.05, interval_sec)  # undgå 0 og alt for aggressiv polling

    samples_per_step = int(acq.get("samples_per_step") or 1)
    samples_per_step = max(1, samples_per_step)

    # total steps = antal intervaller * samples_per_step
    total_intervals = int((duration_sec + interval_sec - 1) // interval_sec) if duration_sec > 0 else 0
    total_steps = int(total_intervals * samples_per_step) if total_intervals > 0 else 0
    if total_steps <= 0:
        total_steps = 1

    _run_state.update({
        "state": "running",
        "started_at": datetime.now().isoformat(),
        "elapsed_sec": 0.0,
        "duration_sec": int(duration_sec),
        "current_step": 1,
        "total_steps": total_steps,
        "profile_name": cfg.get("name"),
        "error": None,
    })

    step = 0
    next_tick = started

    while not stop_event.is_set():
        now = time.time()

        # slut hvis duration nået
        if duration_sec > 0 and (now - started) >= duration_sec:
            break

        # vent til næste tick
        if now < next_tick:
            await asyncio.sleep(min(0.2, next_tick - now))
            continue

        # “tick”
        elapsed = now - started
        step = min(total_steps, step + 1)

        _run_state["elapsed_sec"] = float(elapsed)
        _run_state["current_step"] = int(step)

        # push et datapunkt som frontend kan bruge (fx til playhead)
        _live_ticks.append({
            "t": elapsed,                 # sekunder siden start
            "step": int(step),
            "ts": datetime.now().isoformat()
        })

        next_tick += interval_sec / samples_per_step

    _run_state.update({"state": "stopped"})

from shared_modbus_manager import reset_shared_modbus_manager   # <-- tilføj/importér

@app.post("/api/run/start")
async def run_start(payload: Dict):
    global _runner_task, _runner_stop, _log_task, _log_path

    try:
        cfg = payload.get("config", payload)

        duration_min = (
            cfg.get("duration_minutes")
            or (cfg.get("test_parameters", {}) or {}).get("duration_minutes")
            or 0
        )
        duration_sec = int(float(duration_min) * 60)

        acq = cfg.get("acquisition", {}) or {}
        interval_sec = float(acq.get("interval_sec") or 1.0)
        samples_per_step = int(acq.get("samples_per_step") or 1)
        if interval_sec <= 0:
            interval_sec = 1.0

        total_intervals = int((duration_sec + interval_sec - 1) // interval_sec) if duration_sec > 0 else 0
        total_steps = int(total_intervals * max(1, samples_per_step)) if total_intervals > 0 else 0

        # Stop evt. gammel task
        if _runner_stop:
            _runner_stop.set()
        if _runner_task and not _runner_task.done():
            try:
                await asyncio.wait_for(_runner_task, timeout=2.0)
            except Exception:
                _runner_task.cancel()
                try:
                    await _runner_task   # <-- RET: var _run_task før
                except Exception:
                    pass

        # Stop evt. gammel logger-task
        if _log_task and not _log_task.done():
            _log_task.cancel()
            try:
                await _log_task
            except Exception:
                pass
        _log_task = None
        _log_path = None

        # <-- INDSÆT HER: tving RS485/Modbus porten lukket mellem runs
        try:
            reset_shared_modbus_manager()
        except Exception:
            pass

        # NULSTIL stop-event
        _runner_stop = threading.Event()

        _run_state.update({
            "state": "running",
            "started_at": datetime.now().isoformat(),
            "elapsed_sec": 0.0,
            "duration_sec": duration_sec,
            "current_step": 1 if total_steps > 0 else 0,
            "total_steps": total_steps,
            "profile_name": cfg.get("name") or (cfg.get("test_parameters", {}) or {}).get("test_name"),
            "error": None,
        })

        # Create JSONL run log + start logger task
        profile_name = _run_state.get("profile_name") or "profile"
        safe_name = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in str(profile_name)])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_path = _log_runs_dir() / f"{ts}_{safe_name}.jsonl"
        _run_state["log_path"] = str(_log_path)
        sample_period_sec = float(interval_sec) / float(max(1, samples_per_step))
        _log_task = asyncio.create_task(_log_loop(sample_period_sec))

        # Start runner-tasken
        _runner_task = asyncio.create_task(run_ticks(interval_sec))

        return {"status": "ok", "run": _run_state}

    except Exception as e:
        _run_state.update({"state": "stopped", "error": f"run_start failed: {e}"})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/run/stop")
async def run_stop():
    global _run_task, _run_stop_event

    if _run_stop_event:
        _run_stop_event.set()

    if _run_task and not _run_task.done():
        try:
            await asyncio.wait_for(_run_task, timeout=10.0)
        except asyncio.TimeoutError:
            _run_task.cancel()
            try:
                await _run_task
            except Exception:
                pass
        except Exception:
            # hvis den fejler, cancel og await alligevel
            _run_task.cancel()
            try:
                await _run_task
            except Exception:
                pass

    # VIGTIGT: tving RS485/modbus til at lukke mellem runs
    # Stop logger task
    if _log_task and not _log_task.done():
        _log_task.cancel()
        try:
            await _log_task
        except Exception:
            pass
    _log_task = None
    _log_path = None

    try:
        reset_shared_modbus_manager()
    except Exception:
        pass

    _run_task = None
    _run_state.update({"state": "stopped"})
    return {"status": "ok", "run": _run_state}

@app.post("/api/omron/command")
async def send_omron_command(command: OmronCommand):
    """
    Send command to Omron E5CC temperature controller.
    
    Actions: read_pv, read_sv, write_sv
    """
    async with _rs485_lock:
        try:
            # Find FTDI port if not specified
            port = command.port
            if not port:
                ports = discover_serial_ports()
                ftdi_ports = ports.get("ftdi", [])
                if not ftdi_ports:
                    raise HTTPException(status_code=404, detail="No FTDI device found for RS485")
                port = ftdi_ports[0]["device"]
            
            # Create E5CC tool instance
            # Using shared modbus-compatible settings
            # Note: Both E5CC and VFD will use shared modbus connection
            tool = E5CCTool(
                port=port,
                baudrate=9600,    # Standardized baudrate for shared connection
                parity='N',       # Standardized parity for shared connection
                bytesize=8,
                stopbits=1,
                timeout=2.0,      # Increased timeout for shared connection
                unit_id=2,        # E5CC unit ID
                pv_address=0x2000,
                sv_address=0x2103,
                scale=1.0,
                debug=False
            )
            
            try:
                result = {
                    "action": command.action,
                    "port": port,
                    "timestamp": datetime.now().isoformat(),
                    "success": True
                }
                
                if command.action == "read_pv":
                    pv = tool.read_pv_c()
                    result.update({
                        "temperature_c": pv,
                        "type": "process_value"
                    })
                
                elif command.action == "read_sv":
                    sv = tool.read_sv_c()
                    result.update({
                        "temperature_c": sv,
                        "type": "setpoint_value"
                    })
                
                elif command.action == "write_sv":
                    if command.value is None:
                        raise HTTPException(status_code=400, detail="Value required for write_sv action")
                    tool.write_sv_c(command.value)
                    result.update({
                        "temperature_c": command.value,
                        "type": "setpoint_written"
                    })
                
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown action: {command.action}")
                
                return result
                
            finally:
                tool.close()
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Omron E5CC communication failed: {str(e)}")

@app.get("/api/omron/status")
async def get_omron_status():
    """Get current Omron E5CC temperature readings (PV and SV).

    Note: When a test is running, we avoid re-opening the RS485 port from polling
    endpoints (this can cause Errno 11 due to pyserial exclusive locking). In that
    case we serve the last known values cached by the last successful read.
    """
    if _run_state.get("state") == "running" and _omron_last_good:
        return dict(_omron_last_good)

    async with _rs485_lock:
        # retry a few times if the port is temporarily busy (Errno 11)
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                from hardware_discovery import discover_serial_ports
                ports = discover_serial_ports()
                ftdi_ports = ports.get("ftdi", [])

                if not ftdi_ports:
                    resp = {
                        "status": "no_device",
                        "error": "No FTDI device found for RS485 communication",
                    }
                    _omron_last_good.clear(); _omron_last_good.update(resp)
                    return resp

                port = ftdi_ports[0]["device"]

                tool = E5CCTool(
                    port=port,
                    baudrate=9600,
                    parity="N",
                    bytesize=8,
                    stopbits=1,
                    timeout=2.0,
                    unit_id=2,  # E5CC unit ID
                    pv_address=0x2000,
                    sv_address=0x2103,
                    scale=1.0,
                    debug=False,
                )

                try:
                    pv = tool.read_pv_c()
                    sv = tool.read_sv_c()
                    resp = {
                        "status": "connected",
                        "port": port,
                        "timestamp": datetime.now().isoformat(),
                        "process_value_c": pv,
                        "setpoint_value_c": sv,
                        "unit_id": 2,
                        "last_read": datetime.now().isoformat(),
                    }
                    _omron_last_good.clear(); _omron_last_good.update(resp)
                    return resp
                finally:
                    tool.close()

            except Exception as e:
                last_exc = e
                if attempt < 2 and _is_resource_busy_exc(e):
                    await asyncio.sleep(0.05)
                    continue

                # If busy, serve last known values if available
                if _is_resource_busy_exc(e) and _omron_last_good:
                    resp = dict(_omron_last_good)
                    resp["status"] = "busy"
                    resp["error"] = str(e)
                    return resp

                resp = {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}
                _omron_last_good.clear(); _omron_last_good.update(resp)
                return resp

        # exhausted retries
        if _omron_last_good:
            resp = dict(_omron_last_good)
            resp["status"] = "busy"
            resp["error"] = str(last_exc) if last_exc else "RS485 busy"
            return resp
        return {"status": "error", "error": str(last_exc) if last_exc else "Unknown", "timestamp": datetime.now().isoformat()}

# --- RS510 VFD Control Endpoints ---

# --- RS510 VFD Control Endpoints ---

@app.get("/api/vfd/status")
async def get_vfd_status():
    """Get current RS510 VFD status and readings.

    During an active test we serve cached values to avoid RS485 re-open storms.
    """
    if _run_state.get("state") == "running" and _vfd_last_good:
        return dict(_vfd_last_good)

    async with _rs485_lock:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                from hardware_discovery import discover_serial_ports
                ports = discover_serial_ports()
                ftdi_ports = ports.get("ftdi", [])

                if not ftdi_ports:
                    resp = {"status": "no_device", "error": "No FTDI device found for RS485 communication"}
                    _vfd_last_good.clear(); _vfd_last_good.update(resp)
                    return resp

                port = ftdi_ports[0]["device"]

                vfd = RS510VFDController(
                    port=port,
                    slave_id=3,
                    baudrate=9600,
                    timeout=2.0,
                    debug=False,
                )

                if not vfd.connect():
                    resp = {"status": "connection_failed", "error": "Failed to connect to RS510 VFD", "port": port}
                    _vfd_last_good.clear(); _vfd_last_good.update(resp)
                    return resp

                try:
                    state = vfd.get_status()
                    resp = {
                        "status": "connected",
                        "port": port,
                        "slave_id": 3,
                        "frequency_hz": state.frequency_hz,
                        "frequency_command_hz": state.frequency_command_hz,
                        "run_command": state.run_command.name,
                        "vfd_status": state.status.name,
                        "output_current_a": state.output_current_a,
                        "dc_bus_voltage_v": state.dc_bus_voltage_v,
                        "fault_code": state.fault_code,
                        "temperature_c": state.temperature_c,
                        "timestamp": datetime.now().isoformat(),
                    }
                    _vfd_last_good.clear(); _vfd_last_good.update(resp)
                    return resp
                finally:
                    vfd.disconnect()

            except Exception as e:
                last_exc = e
                if attempt < 2 and _is_resource_busy_exc(e):
                    await asyncio.sleep(0.05)
                    continue

                if _is_resource_busy_exc(e) and _vfd_last_good:
                    resp = dict(_vfd_last_good)
                    resp["status"] = "busy"
                    resp["error"] = str(e)
                    return resp

                resp = {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}
                _vfd_last_good.clear(); _vfd_last_good.update(resp)
                return resp

        if _vfd_last_good:
            resp = dict(_vfd_last_good)
            resp["status"] = "busy"
            resp["error"] = str(last_exc) if last_exc else "RS485 busy"
            return resp
        return {"status": "error", "error": str(last_exc) if last_exc else "Unknown", "timestamp": datetime.now().isoformat()}

@app.post("/api/vfd/control")

@app.post("/api/vfd/control")
async def control_vfd(command: VFDCommand):
    """Control RS510 VFD - start, stop, set frequency, etc."""
    async with _rs485_lock:
        try:
            # Find FTDI port
            # hardware_info = discover_hardware()
            # ftdi_ports = hardware_info.get('ports', {}).get('ftdi', [])
            from hardware_discovery import discover_serial_ports
            ports = discover_serial_ports()
            ftdi_ports = ports.get("ftdi", [])
            if not ftdi_ports:
                return {
                    "status": "no_device",
                    "error": "No FTDI device found for RS485 communication"
                }
            
            port = command.port or ftdi_ports[0]['device']
            slave_id = command.slave_id or 3  # Default RS510 VFD address
            
            # Create VFD controller
            vfd = RS510VFDController(
                port=port,
                slave_id=slave_id,
                baudrate=9600,
                timeout=2.0,
                debug=False
            )
            
            if not vfd.connect():
                return {
                    "status": "connection_failed",
                    "error": "Failed to connect to RS510 VFD",
                    "port": port
                }
            
            try:
                success = False
                result_msg = ""
                
                # Execute command
                if command.action == "status":
                    # Just return status
                    state = vfd.get_status()
                    return {
                        "status": "success",
                        "action": command.action,
                        "data": {
                            "frequency_hz": state.frequency_hz,
                            "frequency_command_hz": state.frequency_command_hz,
                            "run_command": state.run_command.name,
                            "vfd_status": state.status.name,
                            "is_running": state.is_running,
                            "is_fault": state.is_fault,
                            "fault_code": state.fault_code,
                            "timestamp": state.timestamp
                        }
                    }
                    
                elif command.action == "set_frequency":
                    if command.frequency_hz is None:
                        return {
                            "status": "error",
                            "error": "Frequency value required for set_frequency command"
                        }
                    success = vfd.set_frequency(command.frequency_hz)
                    result_msg = f"Set frequency to {command.frequency_hz} Hz"
                    
                elif command.action == "start_forward":
                    success = vfd.start_forward(command.frequency_hz)
                    freq_msg = f" at {command.frequency_hz} Hz" if command.frequency_hz else ""
                    result_msg = f"Started motor forward{freq_msg}"
                    
                elif command.action == "start_reverse":
                    success = vfd.start_reverse(command.frequency_hz)
                    freq_msg = f" at {command.frequency_hz} Hz" if command.frequency_hz else ""
                    result_msg = f"Started motor reverse{freq_msg}"
                    
                elif command.action == "stop":
                    success = vfd.stop()
                    result_msg = "Stopped motor (controlled deceleration)"
                    
                elif command.action == "emergency_stop":
                    success = vfd.emergency_stop()
                    result_msg = "Emergency stop executed"
                    
                else:
                    return {
                        "status": "error",
                        "error": f"Unknown action: {command.action}"
                    }
                
                if success:
                    # Get updated status after command
                    import time
                    time.sleep(0.1)  # Brief delay for VFD to process command
                    state = vfd.get_status()
                    
                    return {
                        "status": "success",
                        "action": command.action,
                        "message": result_msg,
                        "current_state": {
                            "frequency_hz": state.frequency_hz,
                            "frequency_command_hz": state.frequency_command_hz,
                            "is_running": state.is_running,
                            "is_fault": state.is_fault,
                            "vfd_status": state.status.name
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "command_failed",
                        "error": f"VFD did not acknowledge command: {command.action}",
                        "action": command.action
                    }
                    
            finally:
                vfd.disconnect()
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "action": command.action,
                "timestamp": datetime.now().isoformat()
            }

@app.get("/api/scope/waveform")
async def get_scope_waveform(channel: str = "CHAN1", points: int = None):
    """
    Get waveform data from oscilloscope channel for dashboard preview.
    Uses dashboard_preview settings from config for optimal performance.
    
    Args:
        channel: Channel to capture (CHAN1, CHAN2, CHAN3, CHAN4)
        points: Number of points to capture (defaults to dashboard_preview.points from config)
    """
    # Use lock to prevent concurrent oscilloscope access
    with _scope_lock:
        try:
            import pyvisa
            import json
            
            # Load config to get scope IP
            config_path = Path(__file__).parent / "config.json"
            if not config_path.exists():
                raise HTTPException(status_code=500, detail="Config file not found")
                
            with open(config_path) as f:
                config = json.load(f)
            
            scope_ip = config.get("scope_ip", "169.254.47.193")
            
            # Use dashboard preview settings if points not specified
            if points is None:
                preview_config = config.get("dashboard_preview", {})
                points = preview_config.get("points", 1000)
            
            # Ensure we don't exceed scope limits  
            points = min(points, 62500)
            
            # Connect to oscilloscope with optimized settings
            rm = pyvisa.ResourceManager('@py')
            scope = rm.open_resource(f'TCPIP::{scope_ip}::INSTR')
            scope.timeout = 15000  # Increased timeout for dashboard preview
            scope.write_termination = '\n'
            scope.read_termination = '\n'
            # Clear any existing errors and reset scope state
            scope.write('*CLS')  # Clear status
            scope.query('*OPC?')  # Wait for operation complete
            
            # Check for errors
            error_response = scope.query('SYST:ERR?')
            if not error_response.startswith('0,"No error"'):
                print(f"Warning: Scope error before acquisition: {error_response}")
            
            # Configure waveform acquisition with proper sequencing and delays
            scope.write(f':WAV:SOUR {channel}')
            scope.query('*OPC?')  # Wait after source selection
            
            scope.write(':WAV:MODE RAW')
            scope.write(':WAV:FORMAT WORD')  
            scope.write(f':WAV:POINTS {points}')  # Use calculated points from config
            
            # Wait for all settings to take effect
            scope.query('*OPC?')
            
            # Get preamble for scaling
            preamble = scope.query(':WAV:PRE?').strip().split(',')
            
            # Parse preamble (Keysight format) with error handling
            try:
                format_type = int(preamble[0])  # 0=BYTE, 1=WORD, 4=ASCII
                acq_type = int(preamble[1])     # 0=NORMAL, 1=PEAK, 2=AVERAGE
                points_count = int(preamble[2])  # Number of data points
                avg_count = int(preamble[3])     # Average count
                x_increment = float(preamble[4]) # Time between points (s)
                x_origin = float(preamble[5])    # Time of first point (s)
                x_reference = int(preamble[6])   # Sample number of x_origin
                y_increment = float(preamble[7]) # Voltage per LSB
                y_origin = float(preamble[8])    # Voltage at center screen
                y_reference = int(preamble[9])   # Sample value at y_origin
            except (ValueError, IndexError) as e:
                raise HTTPException(status_code=500, detail=f"Failed to parse preamble: {preamble[:100]}... Error: {e}")
            
            # Get raw waveform data
            raw_data = scope.query_binary_values(':WAV:DATA?', datatype='h', is_big_endian=True)
            
            # Convert to voltage and time arrays with error handling
            try:
                voltage_data = [(point - y_reference) * y_increment + y_origin for point in raw_data]
                time_data = [x_origin + (i - x_reference) * x_increment for i in range(len(raw_data))]
                
                # Validate data
                if not voltage_data or not time_data:
                    raise ValueError("Empty data arrays")
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Data conversion failed: {e}. Raw data length: {len(raw_data) if raw_data else 0}")
            
            # Prepare data for React (limit to reasonable size for web)
            max_web_points = min(len(voltage_data), 2000)  # Limit for web display
            step = len(voltage_data) // max_web_points if len(voltage_data) > max_web_points else 1
            
            web_voltage = voltage_data[::step][:max_web_points]
            web_time = time_data[::step][:max_web_points]
            
            return {
                "channel": channel,
                "points_requested": points,
                "points_captured": len(raw_data),
                "points_returned": len(web_voltage),
                "sample_rate_hz": 1.0 / x_increment if x_increment > 0 else 0,
                "time_span_s": (time_data[-1] - time_data[0]) if len(time_data) > 1 else 0,
                "voltage_range_v": [min(voltage_data), max(voltage_data)] if voltage_data else [0, 0],
                "waveform": [
                    {"x": t, "y": v} for t, v in zip(web_time, web_voltage)
                ],
                "timestamp": datetime.now().isoformat(),
                "acquisition_info": {
                    "format": "WORD",
                    "mode": "RAW",
                    "avg_count": avg_count,
                    "x_increment": x_increment,
                    "y_increment": y_increment,
                    "preview_mode": True,
                    "decimation_ratio": config.get("dashboard_preview", {}).get("decimation_ratio", 250)
                }
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Oscilloscope waveform capture failed: {str(e)}")
        finally:
            if 'scope' in locals():
                scope.close()

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Test Rig API Server...")
    print("📍 API will be available at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("🔄 React CORS enabled for: http://localhost:3000")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )