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
import subprocess
import sys
import re
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import threading

# --- Optional: scope acquisition loop (HDF5) ---
# We start this when frontend presses Start, mirroring acquire_scope_data.py main()
try:
    import acquire_scope_data as _acquire_scope_data
except Exception:
    _acquire_scope_data = None

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



# --- Shelly MQTT Manager ---

class ShellyMQTTManager:
    """Manages persistent MQTT connection to Shelly Pro 4PM."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config = None
        self._client = None
        self._connected = False
        self._channel_state: Dict[int, Dict] = {}
        self._lock = threading.Lock()
        self._msg_id = 100
        self._load_config()
        self._start()

    def _load_config(self):
        try:
            with open(self.config_path) as f:
                self._config = json.load(f)
        except Exception as e:
            print(f"[Shelly] Config load failed: {e}")
            self._config = None

    def _start(self):
        if not self._config:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[Shelly] paho-mqtt not installed — run: pip install paho-mqtt")
            return

        mqtt_cfg = self._config.get("mqtt", {})
        device_id = self._config.get("device_id", "")
        client = mqtt.Client(client_id=mqtt_cfg.get("client_id", "testrig_shelly"))
        if mqtt_cfg.get("username"):
            client.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password", ""))

        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                self._connected = True
                c.subscribe(f"{device_id}/#")
                print("[Shelly] Connected and subscribed")
                # Request current status for all 4 channels
                import threading as _threading, time as _time
                def _fetch_initial():
                    _time.sleep(0.5)
                    for ch in range(4):
                        self._msg_id += 1
                        p = json.dumps({"id": self._msg_id, "src": "testrig",
                                        "method": "Switch.GetStatus", "params": {"id": ch}})
                        c.publish(f"{device_id}/rpc", p)
                        _time.sleep(0.2)
                _threading.Thread(target=_fetch_initial, daemon=True).start()
            else:
                print(f"[Shelly] Connect failed rc={rc}")

        def on_disconnect(c, userdata, rc):
            self._connected = False
            print(f"[Shelly] Disconnected rc={rc}")

        def on_message(c, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
                topic = msg.topic
                if "/status/switch:" in topic:
                    ch_id = int(topic.split("switch:")[-1])
                    with self._lock:
                        existing = self._channel_state.get(ch_id, {})
                        existing.update(payload)
                        self._channel_state[ch_id] = existing
                elif "/events/rpc" in topic:
                    params = payload.get("params", {})
                    for key, val in params.items():
                        if key.startswith("switch:"):
                            ch_id = int(key.split("switch:")[-1])
                            with self._lock:
                                existing = self._channel_state.get(ch_id, {})
                                if isinstance(val, dict):
                                    existing.update(val)
                                self._channel_state[ch_id] = existing

                # rpc/response — reply to Switch.GetStatus
                elif "/rpc/response" in topic:
                    result = payload.get("result", {})
                    if isinstance(result, dict) and "id" in result and "output" in result:
                        ch_id = result["id"]
                        with self._lock:
                            existing = self._channel_state.get(ch_id, {})
                            existing.update(result)
                            self._channel_state[ch_id] = existing
            except Exception:
                pass

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        try:
            client.connect(mqtt_cfg.get("host", "localhost"), mqtt_cfg.get("port", 1883), keepalive=60)
            client.loop_start()
            self._client = client
        except Exception as e:
            print(f"[Shelly] Connection error: {e}")

    def get_status(self) -> Dict:
        with self._lock:
            return {"connected": self._connected, "channels": dict(self._channel_state)}

    def set_switch(self, channel_id: int, on: bool) -> bool:
        if not self._client or not self._connected:
            return False
        device_id = self._config.get("device_id", "")
        self._msg_id += 1
        payload = json.dumps({
            "id": self._msg_id, "src": "testrig",
            "method": "Switch.Set", "params": {"id": channel_id, "on": on}
        })
        result = self._client.publish(f"{device_id}/rpc", payload)
        return result.rc == 0

    def get_channel_config(self) -> list:
        if not self._config:
            return []
        return self._config.get("channels", [])

    def reload_config(self):
        self._load_config()


_shelly_manager: Optional[Any] = None
_shelly_manager_lock = threading.Lock()


def _get_shelly_manager():
    global _shelly_manager
    with _shelly_manager_lock:
        if _shelly_manager is None:
            cfg = Path(__file__).parent / "shelly_config.json"
            if cfg.exists():
                _shelly_manager = ShellyMQTTManager(str(cfg))
        return _shelly_manager

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

# live “tick” data til frontend
_live_ticks = deque(maxlen=5000)  # gem de seneste N samples

_run_task: asyncio.Task | None = None
_run_stop_event = asyncio.Event()

# --- Scope acquisition task state (runs acquire_scope_data.acquire_loop in a thread) ---
_scope_acq_task: Optional[asyncio.Task] = None
_scope_acq_last_error: Optional[str] = None
_scope_acq_running: bool = False

async def _scope_acq_runner(cfg: Dict[str, Any]):
    """Run acquire_scope_data.acquire_loop(cfg) in a background thread.

    This mirrors acquire_scope_data.py main() behavior (but cfg is already provided).
    We hold _scope_lock while acquiring to avoid concurrent SCPI commands.
    """
    global _scope_acq_last_error, _scope_acq_running

    if _acquire_scope_data is None:
        _scope_acq_last_error = "acquire_scope_data.py not importable"
        return

    try:
        _scope_acq_last_error = None
        _scope_acq_running = True
        # Make sure DEBUG exists (keeps parity with acquire_scope_data.py)
        try:
            _acquire_scope_data.DEBUG = bool((cfg.get("acquisition", {}) or {}).get("debug", False))
        except Exception:
            pass

        def _do():
            with _scope_lock:
                _acquire_scope_data.acquire_loop(cfg)

        await asyncio.to_thread(_do)

    except Exception as e:
        _scope_acq_last_error = str(e)
    finally:
        _scope_acq_running = False


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
    "state": "idle",          # idle | running | stopped | error
    "started_at": None,       # ISO timestamp string
    "elapsed_sec": 0.0,
    "duration_sec": 0,
    "current_step": 0,
    "total_steps": 0,
    "sweep_current": 0,
    "sweep_total": 0,
    "profile_name": None,
    "run_folder": None,
    "pid": None,
    "stdout_tail": [],        # last N lines
    "error": None,
    # Live telemetry — updated by reader thread from [runner] JSON lines
    "live_telemetry": {
        "rpm_target": None,
        "rpm_meas": None,
        "temp_target": None,
        "omron_pv_c": None,
        "omron_sv_c": None,
        "vfd_cmd_hz": None,
        "vfd_is_running": None,
        "mass_g": None,
        "ts": None,
    },
}

# Subprocess-driven run (acquire_scope_data.py)
_run_proc = None
_run_proc_thread = None
_run_proc_stop = None
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
    # PATCH: avoid opening serial when runner owns hardware
    if _run_state.get("state") in ("running", "stopping"):
        return {
            "status": "runner_active",
            "timestamp": datetime.now().isoformat()
        }

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

@app.get("/api/hdf5/status")
async def get_hdf5_status():
    """
    Return real HDF5 file status for the current/latest run.
    Reads file size, sweep count and channel count directly from disk.
    """
    import os

    run_folder = _run_state.get("run_folder")
    h5_path = None

    # Try run_folder first (active or last run)
    if run_folder:
        try:
            candidates = list(Path(run_folder).glob("scope_*.h5"))
            if candidates:
                h5_path = str(sorted(candidates)[-1])
        except Exception:
            pass

    # Fallback: find latest .h5 in py/data/
    if not h5_path:
        try:
            data_dir = Path(__file__).parent / "data"
            candidates = list(data_dir.rglob("scope_*.h5")) + list(data_dir.glob("*.h5"))
            if candidates:
                h5_path = str(max(candidates, key=os.path.getmtime))
        except Exception:
            pass

    if not h5_path or not os.path.exists(h5_path):
        return {
            "filename": None,
            "created": None,
            "isActive": _run_state.get("state") == "running",
            "currentSizeBytes": 0,
            "totalSweeps": 0,
            "activeChannels": 0,
            "recordingDuration": 0,
            "error": "No HDF5 file found"
        }

    try:
        size_bytes = os.path.getsize(h5_path)
        mtime = os.path.getmtime(h5_path)
        created = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y, %H:%M:%S")
        filename = os.path.basename(h5_path)

        total_sweeps = _run_state.get("sweep_current", 0)

        try:
            cfg = json.load(open(Path(__file__).parent / "config.json"))
            active_channels = len([c for c in cfg.get("channels", []) if c.get("enabled", True)])
        except Exception:
            active_channels = 0

        recording_duration = int(_run_state.get("elapsed_sec", 0))

        # Disk space
        import shutil
        disk = shutil.disk_usage(os.path.dirname(h5_path))

        return {
            "filename": filename,
            "created": created,
            "isActive": _run_state.get("state") == "running",
            "currentSizeBytes": size_bytes,
            "diskFreeBytes": disk.free,
            "diskTotalBytes": disk.total,
            "totalSweeps": total_sweeps,
            "activeChannels": active_channels,
            "recordingDuration": recording_duration,
        }

    except Exception as e:
        return {
            "filename": os.path.basename(h5_path) if h5_path else None,
            "isActive": _run_state.get("state") == "running",
            "currentSizeBytes": 0,
            "totalSweeps": 0,
            "activeChannels": 0,
            "recordingDuration": 0,
            "error": str(e)
        }

@app.get("/api/telemetry")
async def get_telemetry():
    """
    Single telemetry endpoint for the UI.
    - During a run: returns live_telemetry from _run_state (updated by reader thread from [runner] lines)
    - When idle: reads directly from RP2040 and Omron hardware
    """
    # --- During a run: use live_telemetry from runner ---
    if _run_state.get("state") in ("running", "stopping"):
        t = _run_state.get("live_telemetry") or {}
        return {
            "source": "runner",
            "state": _run_state.get("state"),
            "rpm":    t.get("rpm_meas"),
            "rpm_target": t.get("rpm_target"),
            "tempC":  t.get("omron_pv_c"),
            "temp_target": t.get("temp_target"),
            "vfd_hz": t.get("vfd_cmd_hz"),
            "vfd_running": t.get("vfd_is_running"),
            "massG":  t.get("mass_g"),
            "ts":     t.get("ts") or _now_iso(),
        }

    # --- Idle: read hardware directly ---
    rpm   = None
    massG = None
    tempC = None

    # RP2040
    try:
        ports = discover_serial_ports()
        rp_ports = ports.get("rp2040", [])
        if rp_ports:
            port = rp_ports[0].get("device")
            if port:
                import serial as _serial
                with _serial.Serial(port, 115200, timeout=2.0) as ser:
                    import time as _time
                    ser.write(b"SPEED?\r\n")
                    _time.sleep(0.15)
                    line = ser.readline().decode("ascii", errors="ignore").strip()
                    import re as _re
                    m = _re.search(r"rpm=([\d.]+)", line)
                    if m:
                        rpm = float(m.group(1))

                    ser.write(b"LOAD?\r\n")
                    _time.sleep(0.15)
                    line = ser.readline().decode("ascii", errors="ignore").strip()
                    m = _re.search(r"mass_g=([\d.]+)", line)
                    if m:
                        massG = float(m.group(1))
    except Exception:
        pass

    # Omron temperature
    try:
        async with _rs485_lock:
            ports = discover_serial_ports()
            ftdi_ports = ports.get("ftdi", [])
            if ftdi_ports:
                port = ftdi_ports[0]["device"]
                tool = E5CCTool(
                    port=port, baudrate=9600, parity="N", bytesize=8, stopbits=1,
                    timeout=2.0, unit_id=2, pv_address=0x2000, sv_address=0x2103,
                    scale=1.0, debug=False
                )
                try:
                    tempC = tool.read_pv_c()
                finally:
                    tool.close()
    except Exception:
        pass

    return {
        "source": "hardware",
        "state": _run_state.get("state", "idle"),
        "rpm":   rpm,
        "tempC": tempC,
        "massG": massG,
        "ts":    _now_iso(),
    }

@app.get("/api/run/status")
async def run_status():
    """Return current run status for frontend."""
    if _run_state.get("state") == "running" and _run_state.get("started_at"):
        try:
            start_dt = datetime.fromisoformat(_run_state["started_at"])
            _run_state["elapsed_sec"] = max(0.0, (datetime.now() - start_dt).total_seconds())
        except Exception:
            pass
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
    """
    Start a full automated test by launching acquire_scope_data.py as a subprocess.

    Expected payload from UI (existing):
      - configPath: "/config/<profile>.json" (selected profile)
      - (optional) config: object (ignored if configPath provided)
      - (optional) debug: bool
    """
    global _run_proc, _run_proc_thread, _run_proc_stop

    try:
        # Resolve profile path (same folder as /api/config/profiles)
        config_dir = Path(__file__).parent.parent / "react" / "public" / "config"

        profile_path = payload.get("profilePath") or payload.get("configPath")
        cfg_obj = payload.get("config")

        resolved_profile = None
        profile_name = None
        duration_sec = 0

        if isinstance(profile_path, str) and profile_path:
            # UI sends "/config/<file>.json"
            fname = profile_path.split("/")[-1]
            candidate = config_dir / fname
            if not candidate.exists():
                raise HTTPException(status_code=404, detail=f"Profile not found: {fname}")
            resolved_profile = candidate
            with open(candidate, "r") as f:
                cfg_obj = json.load(f)
        elif isinstance(cfg_obj, dict):
            # Fallback: accept inline config, write it to a temp profile file in config_dir
            config_dir.mkdir(parents=True, exist_ok=True)
            fname = f"inline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            resolved_profile = config_dir / fname
            with open(resolved_profile, "w") as f:
                json.dump(cfg_obj, f, indent=2)
        else:
            raise HTTPException(status_code=400, detail="Missing configPath/profilePath or config object")

        profile_name = (cfg_obj.get("name")
                        or (cfg_obj.get("test_parameters", {}) or {}).get("test_name")
                        or resolved_profile.stem)

        duration_min = (
            cfg_obj.get("duration_minutes")
            or (cfg_obj.get("test_parameters", {}) or {}).get("duration_minutes")
            or 0
        )
        duration_sec = int(float(duration_min) * 60)

        # Stop any existing run
        await run_stop()

        # Reset RS485/modbus manager between runs (if available)
        try:
            reset_shared_modbus_manager()
        except Exception:
            pass

        # Prepare state
        _run_state.update({
            "state": "running",
            "started_at": datetime.now().isoformat(),
            "elapsed_sec": 0.0,
            "duration_sec": duration_sec,
            "current_step": 0,
            "total_steps": 0,
            "sweep_current": 0,
            "sweep_total": 0,
            "profile_name": profile_name,
            "run_folder": None,
            "pid": None,
            "stdout_tail": [],
            "error": None,
        })

        # Build command
        py_dir = Path(__file__).parent
        script = py_dir / "acquire_scope_data.py"
        config_json = py_dir / "config.json"

        if not script.exists():
            raise HTTPException(status_code=500, detail=f"Missing {script}")
        if not config_json.exists():
            raise HTTPException(status_code=500, detail=f"Missing {config_json}")

        cmd = [sys.executable, "-u", str(script), str(config_json), str(resolved_profile)]
        if payload.get("debug", True):
            cmd.append("--debug")

        _run_proc_stop = threading.Event()

        # Start subprocess
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        _run_proc = subprocess.Popen(
            cmd,
            cwd=str(py_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            start_new_session=True,  # new process group for clean stop (SIGINT)
            env=env,
        )
        _run_state["pid"] = _run_proc.pid

        # Reader thread updates _run_state by parsing stdout
        def _reader():
            try:
                line_re_sweep = re.compile(r"Sweep\s+(\d+)/(\d+)")
                line_re_run_folder = re.compile(r"^Run folder:\s*(.+)\s*$")
                while True:
                    if _run_proc_stop.is_set():
                        break
                    line = _run_proc.stdout.readline() if _run_proc and _run_proc.stdout else ""
                    if not line:
                        break
                    line = line.rstrip("\n")
                    # keep tail
                    tail = _run_state.get("stdout_tail") or []
                    tail.append(line)
                    if len(tail) > 200:
                        tail = tail[-200:]
                    _run_state["stdout_tail"] = tail

                    # parse runner JSON lines: [runner] {...}
                    if line.startswith("[runner] "):
                        try:
                            j = json.loads(line[len("[runner] "):])
                            if "elapsed_sec" in j:
                                _run_state["elapsed_sec"] = float(j["elapsed_sec"])
                            if "current_step" in j:
                                _run_state["current_step"] = int(j["current_step"])
                            if "total_steps" in j:
                                _run_state["total_steps"] = int(j["total_steps"])
                            if "log_path" in j:
                                _run_state["log_path"] = j["log_path"]
                            if j.get("stop_reason"):
                                _run_state["stop_reason"] = j["stop_reason"]

                            # Live telemetry fields from test_runner update_cb
                            telem_keys = ("rpm_target", "rpm_meas", "temp_target",
                                          "omron_pv_c", "omron_sv_c",
                                          "vfd_cmd_hz", "vfd_is_running", "mass_g")
                            telem = _run_state.get("live_telemetry", {})
                            updated = False
                            for k in telem_keys:
                                if k in j:
                                    telem[k] = j[k]
                                    updated = True
                            if updated:
                                telem["ts"] = _now_iso()
                                _run_state["live_telemetry"] = telem
                        except Exception:
                            pass

                    m = line_re_sweep.search(line)
                    if m:
                        _run_state["sweep_current"] = int(m.group(1))
                        _run_state["sweep_total"] = int(m.group(2))

                    m2 = line_re_run_folder.search(line)
                    if m2:
                        _run_state["run_folder"] = m2.group(1).strip()

                # Process ended. stdout EOF only means the child closed its pipe;
                # it may not be reaped yet, so poll() can still return None and a
                # cleanly finished run gets reported as an error. Wait for the real
                # exit code instead of racing the reaper.
                rc = None
                if _run_proc:
                    try:
                        rc = _run_proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        rc = _run_proc.poll()

                if rc == 0:
                    _run_state["state"] = "stopped"
                elif rc is None:
                    _run_state["state"] = "error"
                    _run_state["error"] = _run_state.get("error") or "runner did not exit after its output stream closed"
                else:
                    _run_state["state"] = "error"
                    _run_state["error"] = _run_state.get("error") or f"acquire_scope_data exited with code {rc}"
            except Exception as e:
                _run_state["state"] = "error"
                _run_state["error"] = f"reader failed: {e}"
            finally:
                pass

        _run_proc_thread = threading.Thread(target=_reader, daemon=True)
        _run_proc_thread.start()

        return {"status": "ok", "run": _run_state}

    except HTTPException:
        raise
    except Exception as e:
        _run_state.update({"state": "error", "error": f"run_start failed: {e}"})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/run/stop")
async def run_stop():
    """
    Stop the running acquire_scope_data.py subprocess cleanly so:
      - motor/VFD stops (process exits)
      - HDF5 is flushed/closed (SIGINT first)

    Requires the subprocess to be started with start_new_session=True so we can signal the process group.
    """
    global _run_proc, _run_proc_thread, _run_proc_stop

    # mark state
    if _run_state.get("state") == "running":
        _run_state["state"] = "stopping"
        _run_state["stop_reason"] = _run_state.get("stop_reason") or "stopped_by_user"

    proc = _run_proc
    reader_thr = _run_proc_thread
    stop_evt = _run_proc_stop

    if proc and proc.poll() is None:
        import os
        import signal

        def _wait(timeout_s: float) -> bool:
            try:
                proc.wait(timeout=timeout_s)
                return True
            except Exception:
                return False

        pgid = None
        try:
            pgid = os.getpgid(proc.pid)
        except Exception:
            pgid = None

        # 1) SIGINT (graceful)
        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGINT)
            # PATCH: always signal main process as well
            proc.send_signal(signal.SIGINT)
        except Exception:
            pass

        _wait(20.0)

        # 2) SIGTERM
        if proc.poll() is None:
            try:
                if pgid is not None:
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            _wait(5.0)

        # 3) SIGKILL
        if proc.poll() is None:
            try:
                if pgid is not None:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            _wait(2.0)

    # now safe to stop reader (do NOT stop it before signalling, otherwise you lose end logs)
    try:
        if stop_evt:
            stop_evt.set()
    except Exception:
        pass

    try:
        if reader_thr and reader_thr.is_alive():
            reader_thr.join(timeout=2.0)
    except Exception:
        pass

    _run_proc = None
    _run_proc_thread = None
    _run_proc_stop = None
    _run_state["pid"] = None
    if _run_state.get("state") in ("running", "stopping"):
        _run_state["state"] = "stopped"

    try:
        reset_shared_modbus_manager()
    except Exception:
        pass

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
    # PATCH: runner owns RS485 when running
    if _run_state.get("state") in ("running", "stopping"):
        return dict(_omron_last_good) if _omron_last_good else {
            "status": "runner_active",
            "timestamp": datetime.now().isoformat()
        }

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
    # PATCH: runner owns RS485 when running
    if _run_state.get("state") in ("running", "stopping"):
        return dict(_vfd_last_good) if _vfd_last_good else {
            "status": "runner_active",
            "timestamp": datetime.now().isoformat()
        }

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


# ── Azure Blob Storage Upload ────────────────────────────────────────────────

_azure_upload_state = {
    "status": "idle",          # idle | uploading | done | error | cancelled
    "filename": None,
    "container": None,
    "bytes_sent": 0,
    "bytes_total": 0,
    "percent": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
    "blob_url": None,
}
_azure_upload_lock = threading.Lock()
_azure_upload_cancel = threading.Event()


def _get_azure_blob_service():
    """Create BlobServiceClient from config.json azure section."""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        raise RuntimeError("config.json not found")

    with open(config_path) as f:
        cfg = json.load(f)

    azure_cfg = cfg.get("azure", {})
    conn_str = azure_cfg.get("connection_string")
    if not conn_str:
        raise RuntimeError("No azure.connection_string in config.json")

    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(conn_str)


def _upload_to_azure_thread(file_path: str, container_name: str, blob_name: str):
    """Background thread: chunked upload with progress tracking and cancel support."""
    global _azure_upload_state
    import os as _os

    try:
        file_size = _os.path.getsize(file_path)
        with _azure_upload_lock:
            _azure_upload_state.update({
                "status": "uploading",
                "filename": _os.path.basename(file_path),
                "container": container_name,
                "bytes_sent": 0,
                "bytes_total": file_size,
                "percent": 0,
                "error": None,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "blob_url": None,
            })

        blob_service = _get_azure_blob_service()

        # Ensure container exists (ignore if already exists)
        try:
            blob_service.create_container(container_name)
        except Exception:
            pass  # container already exists

        container_client = blob_service.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks (faster for large files)
        bytes_uploaded = 0

        with open(file_path, "rb") as f:
            if file_size > CHUNK_SIZE:
                # Staged block upload for large files (progress per chunk)
                from azure.storage.blob import BlobBlock
                block_list = []
                block_id = 0

                while True:
                    # Check cancel flag before each chunk
                    if _azure_upload_cancel.is_set():
                        # Clean up partial blob
                        try:
                            blob_client.delete_blob()
                        except Exception:
                            pass
                        with _azure_upload_lock:
                            _azure_upload_state.update({
                                "status": "cancelled",
                                "finished_at": datetime.now().isoformat(),
                            })
                        return

                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    block_id_str = f"{block_id:06d}"
                    b64_block_id = base64.b64encode(block_id_str.encode()).decode()

                    blob_client.stage_block(b64_block_id, chunk, length=len(chunk))
                    block_list.append(b64_block_id)
                    block_id += 1

                    bytes_uploaded += len(chunk)
                    pct = int((bytes_uploaded / file_size) * 100) if file_size > 0 else 100

                    with _azure_upload_lock:
                        _azure_upload_state["bytes_sent"] = bytes_uploaded
                        _azure_upload_state["percent"] = pct

                # Final cancel check before commit
                if _azure_upload_cancel.is_set():
                    with _azure_upload_lock:
                        _azure_upload_state.update({
                            "status": "cancelled",
                            "finished_at": datetime.now().isoformat(),
                        })
                    return

                blob_client.commit_block_list(
                    [BlobBlock(block_id=bid) for bid in block_list]
                )
            else:
                # Small file: single upload
                data = f.read()
                blob_client.upload_blob(data, overwrite=True)
                bytes_uploaded = file_size
                with _azure_upload_lock:
                    _azure_upload_state["bytes_sent"] = bytes_uploaded
                    _azure_upload_state["percent"] = 100

        with _azure_upload_lock:
            _azure_upload_state.update({
                "status": "done",
                "bytes_sent": file_size,
                "percent": 100,
                "finished_at": datetime.now().isoformat(),
                "blob_url": blob_client.url,
            })

    except Exception as e:
        with _azure_upload_lock:
            _azure_upload_state.update({
                "status": "error",
                "error": str(e),
                "finished_at": datetime.now().isoformat(),
            })


@app.get("/api/azure/files")
async def azure_list_files():
    """List available HDF5 files that can be uploaded."""
    import os as _os

    files = []
    seen = set()

    # 1) Current run folder
    run_folder = _run_state.get("run_folder")
    if run_folder and Path(run_folder).exists():
        for p in Path(run_folder).glob("*.h5"):
            if str(p) not in seen:
                seen.add(str(p))
                files.append(_file_info(p))
        for p in Path(run_folder).glob("*.hdf5"):
            if str(p) not in seen:
                seen.add(str(p))
                files.append(_file_info(p))

    # 2) data/ directory (recursive)
    data_dir = Path(__file__).parent / "data"
    if data_dir.exists():
        for pattern in ("**/*.h5", "**/*.hdf5"):
            for p in data_dir.glob(pattern):
                if str(p) not in seen:
                    seen.add(str(p))
                    files.append(_file_info(p))

    # Sort by modified time, newest first
    files.sort(key=lambda f: f["modified_ts"], reverse=True)

    return {"files": files}


def _file_info(p: Path) -> dict:
    import os as _os
    stat = p.stat()
    return {
        "path": str(p),
        "name": p.name,
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y, %H:%M:%S"),
        "modified_ts": stat.st_mtime,
        "parent": p.parent.name,
    }


@app.post("/api/azure/upload")
async def azure_upload(payload: Dict):
    """
    Start uploading an HDF5 file to Azure Blob Storage.

    Body:
        {
            "container": "data",
            "blob_name": "my_test.h5",    (optional: defaults to filename)
            "file_path": "path/to/file"   (optional: defaults to latest HDF5)
        }
    """
    with _azure_upload_lock:
        if _azure_upload_state["status"] == "uploading":
            raise HTTPException(status_code=409, detail="Upload already in progress")

    container = payload.get("container", "data")
    file_path = payload.get("file_path")

    # Find the HDF5 file if not explicitly provided
    if not file_path:
        run_folder = _run_state.get("run_folder")
        if run_folder:
            candidates = list(Path(run_folder).glob("scope_*.h5"))
            if candidates:
                file_path = str(sorted(candidates)[-1])

        if not file_path:
            data_dir = Path(__file__).parent / "data"
            candidates = list(data_dir.rglob("scope_*.h5")) + list(data_dir.glob("*.h5")) + list(data_dir.rglob("*.hdf5"))
            if candidates:
                file_path = str(max(candidates, key=lambda p: p.stat().st_mtime))

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="No HDF5 file found to upload")

    blob_name = payload.get("blob_name") or Path(file_path).name

    # Verify Azure config before starting thread
    try:
        _get_azure_blob_service()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Azure configuration error: {str(e)}")

    # Clear any previous cancel flag
    _azure_upload_cancel.clear()

    t = threading.Thread(
        target=_upload_to_azure_thread,
        args=(file_path, container, blob_name),
        daemon=True,
    )
    t.start()

    return {
        "status": "started",
        "file": Path(file_path).name,
        "container": container,
        "blob_name": blob_name,
    }


@app.get("/api/azure/upload/status")
async def azure_upload_status():
    """Poll upload progress."""
    with _azure_upload_lock:
        return dict(_azure_upload_state)


@app.post("/api/azure/upload/cancel")
async def azure_upload_cancel():
    """Cancel an in-progress upload."""
    _azure_upload_cancel.set()
    # Wait briefly for thread to notice
    await asyncio.sleep(0.5)
    with _azure_upload_lock:
        if _azure_upload_state["status"] == "uploading":
            _azure_upload_state["status"] = "cancelled"
        return dict(_azure_upload_state)


@app.get("/api/azure/containers")
async def azure_list_containers():
    """List available Azure Blob containers."""
    try:
        blob_service = _get_azure_blob_service()
        containers = []
        try:
            for c in blob_service.list_containers():
                containers.append(c.name)
        except Exception:
            # SAS tokens may not allow listing — return known defaults
            containers = ["data"]
        return {"containers": containers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/shelly/status")
async def shelly_status():
    """
    Get current status of all Shelly channels.
    Returns channel state (on/off, power, current, voltage) plus config names.
    """
    mgr = _get_shelly_manager()
    if not mgr:
        return {"connected": False, "channels": [], "error": "shelly_config.json not found"}

    status = mgr.get_status()
    ch_cfg = {ch["id"]: ch for ch in mgr.get_channel_config()}
    channels = []

    for i in range(4):
        hw = status["channels"].get(i, {})
        cfg = ch_cfg.get(i, {"id": i, "name": f"Channel {i+1}", "description": "", "enabled": True})
        channels.append({
            "id": i,
            "name": cfg.get("name", f"Channel {i+1}"),
            "description": cfg.get("description", ""),
            "enabled": cfg.get("enabled", True),
            "output": hw.get("output", None),
            "apower": hw.get("apower"),
            "current": hw.get("current"),
            "voltage": hw.get("voltage"),
            "temperature_c": hw.get("temperature", {}).get("tC") if isinstance(hw.get("temperature"), dict) else None,
            "aenergy_total": hw.get("aenergy", {}).get("total") if isinstance(hw.get("aenergy"), dict) else None,
        })

    return {
        "connected": status["connected"],
        "channels": channels,
        "ts": _now_iso(),
    }


@app.post("/api/shelly/switch/{channel_id}")
async def shelly_set_switch(channel_id: int, payload: Dict):
    """
    Turn a Shelly channel on or off.
    Body: {"on": true/false}
    """
    mgr = _get_shelly_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Shelly not configured")

    on = payload.get("on")
    if on is None:
        raise HTTPException(status_code=400, detail="Missing 'on' field in body")

    success = mgr.set_switch(channel_id, bool(on))
    if not success:
        raise HTTPException(status_code=503, detail="MQTT not connected or publish failed")

    # Brief wait for device to respond
    await asyncio.sleep(2.0)

    # Return updated status
    return await shelly_status()


@app.post("/api/shelly/reload")
async def shelly_reload():
    """Reload shelly_config.json without restarting."""
    global _shelly_manager
    with _shelly_manager_lock:
        if _shelly_manager:
            _shelly_manager.reload_config()
    return {"status": "ok"}


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