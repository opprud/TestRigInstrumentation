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
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our hardware discovery functions
from hardware_discovery import discover_hardware
from omron_temp_poll import E5CCTool
from rs510_vfd_control import RS510VFDController, VFDCommand, VFDState

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
            ser.write(b'LOAD?\r\n')
            time.sleep(0.1)
            load_response = ser.readline().decode('ascii', errors='ignore').strip()
            
            # Get speed reading
            ser.write(b'SPEED?\r\n')
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
        
        # Create E5CC tool with shared modbus settings
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

# --- RS510 VFD Control Endpoints ---

@app.get("/api/vfd/status")
async def get_vfd_status():
    """Get current RS510 VFD status and readings."""
    try:
        # Find FTDI port (same as Omron)
        hardware_info = discover_hardware()
        ftdi_ports = hardware_info.get('ports', {}).get('ftdi', [])
        if not ftdi_ports:
            return {
                "status": "no_device",
                "error": "No FTDI device found for RS485 communication"
            }
        
        port = ftdi_ports[0]['device']
        
        # Create VFD controller
        vfd = RS510VFDController(
            port=port,
            slave_id=3,  # Default RS510 VFD address (check your VFD configuration)
            baudrate=9600,  # Standard VFD baud rate
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
            # Get VFD status
            state = vfd.get_status()
            
            return {
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
                "is_running": state.is_running,
                "is_fault": state.is_fault,
                "timestamp": state.timestamp
            }
            
        finally:
            vfd.disconnect()
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/vfd/control")
async def control_vfd(command: VFDCommand):
    """Control RS510 VFD - start, stop, set frequency, etc."""
    try:
        # Find FTDI port
        hardware_info = discover_hardware()
        ftdi_ports = hardware_info.get('ports', {}).get('ftdi', [])
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
        reload=True,
        log_level="info"
    )