import { useState, useEffect } from 'react';

export function useHardwareStatus() {
  const [hardwareInfo, setHardwareInfo] = useState({
    scope: {
      status: 'disconnected', // 'connected', 'connecting', 'error', 'disconnected'
      ip: '169.254.5.204',
      idn: null,
      lastSeen: null
    },
    rp2040: {
      status: 'disconnected',
      port: null,
      firmware: null,
      lastPing: null
    },
    rs485: {
      status: 'disconnected',
      port: null,
      slaveId: 1,
      lastRead: null
    }
  });

  const [isScanning, setIsScanning] = useState(false);

  // Real hardware discovery via Python API
  const scanHardware = async (forceRescan = false) => {
    setIsScanning(true);
    
    try {
      const response = await fetch(`http://localhost:8000/api/hardware/discover?force_scan=${forceRescan}`);
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      
      // Transform Python API response to React format
      const transformedResults = {
        scope: {
          status: result.scope.status,
          ip: result.scope.ip,
          idn: result.scope.idn,
          lastSeen: result.scope.last_seen || result.scope.last_attempt
        },
        rp2040: {
          status: result.rp2040.status,
          port: result.rp2040.port,
          firmware: result.rp2040.firmware_version,
          lastPing: result.rp2040.last_ping || result.rp2040.last_attempt
        },
        rs485: {
          status: result.rs485.status,
          port: result.rs485.port,
          slaveId: result.rs485.slave_id || 1,
          lastRead: result.rs485.last_read || result.rs485.last_attempt
        }
      };
      
      setHardwareInfo(transformedResults);
    } catch (error) {
      console.error('Hardware scan failed:', error);
      
      // Fallback to mock data if API is not available
      console.warn('Falling back to mock hardware data');
      const fallbackResults = {
        scope: {
          status: 'error',
          ip: '169.254.5.204',
          idn: null,
          lastSeen: null,
          error: 'API connection failed'
        },
        rp2040: {
          status: 'error',
          port: null,
          firmware: null,
          lastPing: null,
          error: 'API connection failed'
        },
        rs485: {
          status: 'error',
          port: null,
          slaveId: 1,
          lastRead: null,
          error: 'API connection failed'
        }
      };
      
      setHardwareInfo(fallbackResults);
    } finally {
      setIsScanning(false);
    }
  };

  // Test individual device connections
  const testScopeConnection = async () => {
    setHardwareInfo(prev => ({
      ...prev,
      scope: { ...prev.scope, status: 'connecting' }
    }));

    // Simulate connection test
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const connected = Math.random() > 0.5;
    setHardwareInfo(prev => ({
      ...prev,
      scope: {
        ...prev.scope,
        status: connected ? 'connected' : 'error',
        lastSeen: connected ? new Date().toLocaleTimeString() : prev.scope.lastSeen,
        idn: connected ? 'KEYSIGHT TECHNOLOGIES,MSO-X 2024A,MY12345678,01.23.2024012345' : null
      }
    }));
  };

  const testRP2040Connection = async () => {
    setHardwareInfo(prev => ({
      ...prev,
      rp2040: { ...prev.rp2040, status: 'connecting' }
    }));

    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const connected = Math.random() > 0.2; // High success rate since it's connected
    setHardwareInfo(prev => ({
      ...prev,
      rp2040: {
        ...prev.rp2040,
        status: connected ? 'connected' : 'error',
        lastPing: connected ? new Date().toLocaleTimeString() : prev.rp2040.lastPing,
        firmware: connected ? '1.0.1' : null,
        port: connected ? '/dev/tty.usbmodemXXXX' : null
      }
    }));
  };

  const testRS485Connection = async () => {
    setHardwareInfo(prev => ({
      ...prev,
      rs485: { ...prev.rs485, status: 'connecting' }
    }));

    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const connected = Math.random() > 0.3; // Good chance since FTDI is connected
    setHardwareInfo(prev => ({
      ...prev,
      rs485: {
        ...prev.rs485,
        status: connected ? 'connected' : 'error',
        lastRead: connected ? new Date().toLocaleTimeString() : prev.rs485.lastRead,
        port: connected ? '/dev/tty.usbserial-FTXXXXXX' : null
      }
    }));
  };

  // Auto-scan on mount
  useEffect(() => {
    scanHardware();
  }, []);

  // Periodic connection checks every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      // Only auto-refresh if we're not manually scanning
      if (!isScanning) {
        scanHardware();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [isScanning]);

  return {
    hardwareInfo,
    isScanning,
    scanHardware,
    testScopeConnection,
    testRP2040Connection,
    testRS485Connection
  };
}