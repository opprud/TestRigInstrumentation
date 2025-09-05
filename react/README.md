# Test Rig Instrumentation Dashboard

A React-based dashboard for controlling and monitoring the ForeverBearing test rig instrumentation system.

## System Architecture

```
┌─────────────────────┐    HTTP API     ┌──────────────────────┐
│  React Dashboard    │◄──────────────► │   Python Backend    │
│  (Port 3000)        │   localhost:8000 │   (Port 8000)       │
└─────────────────────┘                 └──────────────────────┘
                                                    │
                                                    ▼
                        ┌─────────────────────────────────────────┐
                        │           Hardware Layer                │
                        │                                         │
                        │  ┌─────────────────┐ ┌─────────────────┐│
                        │  │   MSO-X 2024A   │ │  Seeed XIAO     ││
                        │  │  Oscilloscope   │ │  RP2040         ││
                        │  │ (169.254.5.204) │ │ (USB Serial)    ││
                        │  └─────────────────┘ └─────────────────┘│
                        │                                         │
                        │  ┌─────────────────┐                   │
                        │  │   Omron E5CC    │                   │
                        │  │ Temperature     │                   │
                        │  │ Controller      │                   │
                        │  │ (RS485)         │                   │
                        │  └─────────────────┘                   │
                        └─────────────────────────────────────────┘
```

## Quick Start

### 1. Start the Python Backend
```bash
# Navigate to Python directory
cd ../py

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Start the backend API server
python api_server.py
# Server will run on http://localhost:8000
```

### 2. Start the React Dashboard
```bash
# Navigate to React directory
cd react

# Install Node.js dependencies
npm install

# Start development server
npm run dev
# Dashboard will be available at http://localhost:3000
```

### 3. Access the Dashboard
Open your browser to: 
- **Dashboard**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs

## System Integration

### React ↔ Python Communication

The React dashboard communicates with the Python backend through REST API endpoints:

#### Hardware Discovery
- **Endpoint**: `GET http://localhost:8000/api/hardware/discover`
- **Purpose**: Detect and connect to all hardware devices
- **Used by**: `src/hooks/useHardwareStatus.js`

#### Test Configuration  
- **Endpoint**: `GET http://localhost:8000/api/config`
- **Purpose**: Load test profile configurations
- **Used by**: `src/hooks/useTestConfig.js`

#### Data Acquisition
- **Endpoint**: `POST http://localhost:8000/api/acquisition/start`
- **Purpose**: Start data collection from oscilloscope and sensors
- **Used by**: `src/hooks/useHDF5Status.js`

#### Real-time Telemetry
- **Endpoint**: `GET http://localhost:8000/api/telemetry/live` 
- **Purpose**: Get current sensor readings (RPM, temperature, load)
- **Used by**: `src/hooks/useTelemetry.js`

### Configuration Files

#### Test Profiles
Located in `public/config/`:
- `test-profile.json` - Standard 15-minute test
- `endurance-profile.json` - 61-minute long-term test  
- `high-stress-profile.json` - 14-minute aggressive test
- `lub1_validation.json` - 110-minute lubrication test

Each profile defines:
```json
{
  "name": "Profile Name",
  "description": "Test description", 
  "duration_minutes": 15,
  "setpoints": {
    "rpm": [{"time_sec": 0, "value": 1000}, ...],
    "temperature": [{"time_sec": 0, "value": 40}, ...]
  },
  "acquisition": {
    "scope_points": 250000,
    "samples_per_step": 3,
    "interval_sec": 3
  }
}
```

#### Python Backend Config
Located in `../py/config.json`:
```json
{
  "scope_ip": "169.254.5.204",
  "acquisition": {
    "points": 250000,
    "samples": 3,
    "interval_sec": 3
  },
  "channels": [
    {"name": "AE", "source": "CHAN1", "enabled": true},
    {"name": "Accel", "source": "CHAN2", "enabled": true}
  ]
}
```

### Hardware Connections

#### 1. Oscilloscope (MSO-X 2024A)
- **Connection**: Ethernet (IP: 169.254.5.204)
- **Protocol**: SCPI over TCP/IP
- **Channels**: 4 analog inputs (AE probe, accelerometer, ultrasound, temperature)
- **Control**: Python `acquire_scope_data.py`

#### 2. RP2040 Microcontroller
- **Connection**: USB Serial (/dev/tty.usbmodemXXXX)
- **Protocol**: ASCII commands
- **Sensors**: HX711 load cell, tachometer input
- **Commands**:
  - `LOAD?` → Get load cell reading
  - `SPEED?` → Get RPM measurement
  - `TARE` → Zero load cell
- **Control**: Python `util_tool.py`

#### 3. Omron E5CC Temperature Controller
- **Connection**: RS485 serial
- **Protocol**: Modbus RTU
- **Function**: PID temperature control
- **Control**: Python backend RS485 interface

## Development

### React Components Structure
```
src/
├── Dashboard.jsx           # Main dashboard component
├── components/
│   ├── ConfigSelector.jsx  # Test profile selection
│   ├── SectionTitle.jsx    # UI component
│   └── ui/                 # Shadcn UI components
├── hooks/
│   ├── useHardwareStatus.js  # Hardware discovery & status
│   ├── useTestConfig.js      # Test profile management
│   ├── useHDF5Status.js      # Data acquisition control
│   └── useTelemetry.js       # Live sensor data
└── lib/
    └── utils.js            # Utility functions
```

### Key React Hooks

#### `useHardwareStatus()`
- Discovers and monitors hardware connections
- Provides scan functionality for device detection
- Returns status for scope, RP2040, and RS485 devices

#### `useTestConfig(configPath)`
- Loads test profiles from JSON files
- Provides chart data generation for setpoint visualization
- Calculates test duration from setpoints
- Supports manual override mode

#### `useHDF5Status()`
- Controls data acquisition sessions
- Manages HDF5 file creation and metadata
- Tracks sweep counts and file size

#### `useTelemetry()`
- Provides real-time sensor readings
- WebSocket or polling-based updates
- Returns RPM, temperature, and load data

### Building for Production
```bash
# Build optimized production bundle
npm run build

# Preview production build locally
npm run preview
```

### Testing Hardware Integration
1. **Check Python backend health**:
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Test hardware discovery**:
   ```bash  
   curl http://localhost:8000/api/hardware/discover
   ```

3. **Verify configuration loading**:
   ```bash
   curl http://localhost:8000/api/config
   ```

## Troubleshooting

### Common Issues

**Dashboard won't load**: 
- Verify React dev server is running on port 3000
- Check browser console for JavaScript errors

**Hardware not detected**:
- Ensure Python backend is running on port 8000  
- Check physical connections (USB, Ethernet, RS485)
- Review device-specific logs in backend

**Configuration not loading**:
- Verify JSON syntax in config files
- Check file permissions and paths
- Validate setpoint timing consistency

**Data acquisition fails**:
- Confirm oscilloscope IP address (169.254.5.204)
- Test SCPI communication with backend
- Check available disk space for HDF5 files

### Log Files
- **React**: Browser developer console
- **Python Backend**: Terminal output where `api_server.py` is running
- **Hardware**: Individual device logs via backend APIs

## Hardware Requirements

- **Network**: Ethernet connection to oscilloscope
- **USB**: Available ports for RP2040 microcontroller  
- **Serial**: RS485 adapter for temperature controller
- **Storage**: Sufficient disk space for HDF5 data files
- **OS**: macOS, Linux, or Windows with Python 3.8+

## Next Steps

1. **Real-time Charts**: Implement live waveform visualization
2. **Data Export**: Add CSV/Excel export functionality  
3. **Alert System**: Set up threshold-based notifications
4. **Remote Access**: Configure for network deployment
5. **Automated Testing**: Add test sequence automation

---

For detailed hardware specifications and Python backend documentation, see the main project [CLAUDE.md](../CLAUDE.md).