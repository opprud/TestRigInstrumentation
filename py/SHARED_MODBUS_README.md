# Shared Modbus Implementation

This directory now contains a shared Modbus connection manager that allows both the Omron E5CC temperature controller and RS510 VFD to communicate through the same FTDI485 adapter without conflicts.

## Changes Made

### 1. Shared Connection Manager (`shared_modbus_manager.py`)
- Thread-safe Modbus connection management
- Prevents conflicts between multiple devices on same RS485 port
- Automatic connection management and error handling
- Global instance management for efficiency

### 2. Updated Device Controllers
- **`omron_temp_poll.py`**: Now uses shared connection manager
- **`rs510_vfd_control.py`**: Now uses shared connection manager
- Both maintain backward compatibility for standalone use

### 3. FastAPI Integration (`api_server.py`)
- Updated endpoints to use standardized Modbus settings
- Fixed import errors and configuration inconsistencies
- Both devices now use compatible communication parameters

## Device Configuration

### Standard Settings (Shared Connection)
```
Port: /dev/tty.usbserial-FTDI485 (or your FTDI device)
Baudrate: 9600
Parity: None
Data bits: 8
Stop bits: 1
Timeout: 2.0 seconds
```

### Device Addresses
- **Omron E5CC**: Unit ID 4 (was 2)
- **RS510 VFD**: Unit ID 3 (default)

⚠️ **Important**: If your devices are configured with different communication parameters (e.g., E5CC with 57600 baud, Even parity), you'll need to either:
1. Reconfigure the devices to match the standard settings, or
2. Use separate FTDI485 adapters for each device

## Testing the Integration

Use the test script to verify everything works:

```bash
# Test with your FTDI485 port
python3 test_shared_modbus.py --port /dev/tty.usbserial-FTDI485

# Test with debug output
python3 test_shared_modbus.py --port /dev/tty.usbserial-FTDI485 --debug

# Test with custom unit IDs
python3 test_shared_modbus.py --port /dev/tty.usbserial-FTDI485 --e5cc-unit 2 --vfd-unit 1
```

## Configuration Files

- `modbus_config.json`: Documents the shared configuration and device settings
- Check device manuals for correct unit IDs and register addresses

## FastAPI Endpoints

The dashboard can now safely call both temperature and VFD endpoints simultaneously:

- `GET /api/omron/status` - Read E5CC temperature
- `POST /api/omron/command` - Control E5CC setpoint
- `GET /api/vfd/status` - Read VFD status
- `POST /api/vfd/control` - Control VFD operation

## Troubleshooting

1. **Connection Failures**:
   - Verify device unit IDs match configuration
   - Check cable connections and RS485 termination
   - Try original device-specific settings if shared settings fail

2. **Communication Conflicts**:
   - The shared manager serializes all access
   - If you see timeout errors, increase the timeout value
   - Check for proper RS485 wiring (A/B lines, termination)

3. **Unit ID Issues**:
   - E5CC default might be 1, 2, or 4 depending on configuration
   - VFD default might be 1, 2, or 3 depending on configuration
   - Use device configuration software to verify/change unit IDs

## Reverting Changes

If you need to revert to individual connections:

1. Use separate FTDI485 adapters for each device
2. Modify the import statements back to direct pymodbus usage
3. Restore original communication parameters for each device

The shared manager is designed to be transparent - existing code should work with minimal changes.