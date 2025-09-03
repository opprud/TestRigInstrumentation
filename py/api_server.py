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
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our hardware discovery functions
from hardware_discovery import discover_hardware
from test_hardware import main as test_ports
from omron_temp_poll import E5CCTool

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

# --- Global State ---
_last_hardware_scan = None
_hardware_cache_duration = 30  # seconds

# --- API Endpoints ---

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
    Discover and return hardware connection status.
    
    Args:
        force_scan: If True, force a new scan instead of using cache
    """
    global _last_hardware_scan
    
    try:
        # Use cached results if recent and not forcing scan
        if (not force_scan and 
            _last_hardware_scan and 
            (datetime.now() - _last_hardware_scan['timestamp']).total_seconds() < _hardware_cache_duration):
            return _last_hardware_scan['data']
        
        # Load config if available
        config = None
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
        
        # Run hardware discovery
        hardware_info = discover_hardware(config)
        
        # Cache the results
        _last_hardware_scan = {
            'timestamp': datetime.now(),
            'data': hardware_info
        }
        
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
        port = command.port
        if not port:
            hardware_info = discover_hardware()
            rp2040_ports = hardware_info.get('ports', {}).get('rp2040', [])
            if not rp2040_ports:
                raise HTTPException(status_code=404, detail="No RP2040 device found")
            port = rp2040_ports[0]['device']
        
        # Send command
        with serial.Serial(port, 115200, timeout=2.0) as ser:
            ser.write(f'{command.command}\\r\\n'.encode())
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
    """Get detailed RP2040 status including sensor readings."""
    try:
        # Get basic hardware info first
        hardware_info = discover_hardware()
        rp2040_info = hardware_info.get('rp2040', {})
        
        if rp2040_info.get('status') != 'connected':
            return rp2040_info
        
        # Get sensor readings
        port = rp2040_info.get('port')
        if not port:
            raise HTTPException(status_code=404, detail="RP2040 port not found")
        
        import serial
        import time
        
        with serial.Serial(port, 115200, timeout=2.0) as ser:
            # Get load reading
            ser.write(b'LOAD?\\r\\n')
            time.sleep(0.1)
            load_response = ser.readline().decode('ascii', errors='ignore').strip()
            
            # Get speed reading
            ser.write(b'SPEED?\\r\\n')
            time.sleep(0.1)
            speed_response = ser.readline().decode('ascii', errors='ignore').strip()
            
            return {
                **rp2040_info,
                "load_reading": load_response,
                "speed_reading": speed_response,
                "last_update": datetime.now().isoformat()
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RP2040 status check failed: {str(e)}")

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

@app.post("/api/omron/command")
async def send_omron_command(command: OmronCommand):
    """
    Send command to Omron E5CC temperature controller.
    
    Actions: read_pv, read_sv, write_sv
    """
    try:
        # Find FTDI port if not specified
        port = command.port
        if not port:
            hardware_info = discover_hardware()
            ftdi_ports = hardware_info.get('ports', {}).get('ftdi', [])
            if not ftdi_ports:
                raise HTTPException(status_code=404, detail="No FTDI device found for RS485")
            port = ftdi_ports[0]['device']
        
        # Create E5CC tool instance
        # Using default settings from omron_temp_poll.py
        tool = E5CCTool(
            port=port,
            baudrate=57600,
            parity='E',
            bytesize=8,
            stopbits=1,
            timeout=1.5,
            unit_id=4,
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
    """Get current Omron E5CC temperature readings (PV and SV)."""
    try:
        # Find FTDI port
        hardware_info = discover_hardware()
        ftdi_ports = hardware_info.get('ports', {}).get('ftdi', [])
        if not ftdi_ports:
            return {
                "status": "no_device",
                "error": "No FTDI device found for RS485 communication"
            }
        
        port = ftdi_ports[0]['device']
        
        # Create E5CC tool
        tool = E5CCTool(
            port=port,
            baudrate=57600,
            parity='E',
            bytesize=8,
            stopbits=1,
            timeout=1.5,
            unit_id=4,
            pv_address=0x2000,
            sv_address=0x2103,
            scale=1.0,
            debug=False
        )
        
        try:
            # Read both PV and SV
            pv = tool.read_pv_c()
            sv = tool.read_sv_c()
            
            return {
                "status": "connected",
                "port": port,
                "timestamp": datetime.now().isoformat(),
                "process_value_c": pv,
                "setpoint_value_c": sv,
                "unit_id": 4,
                "last_read": datetime.now().isoformat()
            }
            
        finally:
            tool.close()
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

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
        reload=True,
        log_level="info"
    )