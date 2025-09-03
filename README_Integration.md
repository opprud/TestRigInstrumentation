# Python-React Integration Guide

## 🔗 How Python Scripts Connect to React

### Architecture Overview
```
┌─────────────────┐    HTTP API     ┌──────────────────┐    Hardware
│   React Web     │◄──────────────►│   Python FastAPI │◄──────────┐
│   Dashboard     │  Port 3000      │   Backend        │ Port 8000  │
│                 │                 │                  │            │
├─────────────────┤                 ├──────────────────┤            │
│ • Hardware Status│                 │ • Hardware Disc. │            │
│ • Config Mgmt   │                 │ • Serial Comm    │            │
│ • Live Data     │                 │ • SCPI Commands  │            │
│ • Test Control  │                 │ • File I/O       │            │
└─────────────────┘                 └──────────────────┘            │
                                                                     │
                                    ┌─────────────────────────────────┤
                                    │
                                    ▼
                            ┌──────────────────┐
                            │    Hardware      │
                            │                  │
                            │ 🔬 MSO-X 2024A   │
                            │ 🔧 RP2040 Pico   │
                            │ 🌡️ FTDI RS485    │
                            └──────────────────┘
```

## 🚀 Quick Start

### Method 1: Auto Start (Recommended)
```bash
# Start both Python API and React frontend
./start_system.sh
```

### Method 2: Manual Start
```bash
# Terminal 1: Start Python API
cd py
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 api_server.py

# Terminal 2: Start React frontend (already running)
cd react
npm run dev
```

## 🔌 API Endpoints

### Hardware Discovery
```
GET http://localhost:8000/api/hardware/discover
GET http://localhost:8000/api/hardware/discover?force_scan=true
```

### RP2040 Communication
```
POST http://localhost:8000/api/rp2040/command
Body: {"command": "PING"}

GET http://localhost:8000/api/rp2040/status
```

### System Information
```
GET http://localhost:8000/api/system/ports
GET http://localhost:8000/api/health
```

## 🔧 React Integration

### Hardware Status Hook
```javascript
// hooks/useHardwareStatus.js
const response = await fetch('http://localhost:8000/api/hardware/discover');
const result = await response.json();
```

### API Error Handling
- ✅ **API Available**: Shows real hardware status from Python
- ❌ **API Down**: Falls back to mock data with error indicators
- 🔄 **Auto Retry**: Attempts reconnection every 30 seconds

## 📁 File Structure
```
TestRigInstrumentation/
├── py/                          # Python Backend
│   ├── api_server.py           # FastAPI server
│   ├── hardware_discovery.py   # Hardware detection
│   ├── test_hardware.py        # Port testing
│   ├── util_tool.py            # RP2040 communication
│   └── requirements.txt        # Python dependencies
├── react/                       # React Frontend  
│   ├── src/hooks/              # API integration hooks
│   ├── src/components/         # UI components
│   └── package.json            # Node dependencies
└── start_system.sh             # Startup script
```

## 🧪 Testing the Integration

### 1. Test Python Hardware Discovery
```bash
cd py
python3 test_hardware.py
# Should show your connected Pi Pico2 and FTDI cable
```

### 2. Test API Server
```bash
cd py
python3 api_server.py
# Visit: http://localhost:8000/docs
```

### 3. Test React Connection
```bash
# In React dashboard, click "Scan" button
# Check browser console for API calls
# Hardware badges should show real connection status
```

## 🔍 Debugging

### Common Issues
1. **API Connection Failed**
   - Check if Python server is running on port 8000
   - Check CORS settings in api_server.py
   - Look for errors in browser console

2. **Hardware Not Detected**
   - Run `python3 test_hardware.py` to see actual ports
   - Check VID/PID values in hardware_discovery.py
   - Verify device permissions on macOS/Linux

3. **Import Errors**
   - Make sure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python virtual environment is activated

### Debug Endpoints
```
GET http://localhost:8000/                 # API info
GET http://localhost:8000/api/health       # Health check
GET http://localhost:8000/api/system/ports # Raw port list
```

## 🎯 Next Steps

1. **Real Hardware Testing**: Connect your Pi Pico2 and test actual communication
2. **MSO-X Integration**: Connect oscilloscope and test SCPI commands  
3. **Data Pipeline**: Stream real sensor data to React dashboard
4. **Test Automation**: Implement automated test sequences