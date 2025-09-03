import { useState, useEffect, useRef } from 'react';

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState({ 
    ts: Date.now(), 
    rpm: 0, 
    tempC: 0, 
    massG: 0 
  });
  const [connected, setConnected] = useState(false);
  const intervalRef = useRef(null);

  // Fetch real sensor data from the API
  const fetchTelemetryData = async () => {
    try {
      // Fetch Omron temperature data
      const omronResponse = await fetch('http://localhost:8000/api/omron/status');
      const omronData = omronResponse.ok ? await omronResponse.json() : null;

      // Fetch RP2040 data (speed and load)
      const rp2040Response = await fetch('http://localhost:8000/api/rp2040/status');
      const rp2040Data = rp2040Response.ok ? await rp2040Response.json() : null;

      // Parse temperature
      let tempC = 0;
      if (omronData && omronData.status === 'connected') {
        tempC = omronData.process_value_c || 0;
      }

      // Parse speed and load from RP2040
      let rpm = 0;
      let massG = 0;
      if (rp2040Data && rp2040Data.status === 'connected') {
        // Parse speed response (assuming format like "OK 1234")
        if (rp2040Data.speed_reading) {
          const speedMatch = rp2040Data.speed_reading.match(/(\d+\.?\d*)/);
          if (speedMatch) {
            rpm = parseFloat(speedMatch[1]);
          }
        }

        // Parse load response (assuming format like "OK 567.8")
        if (rp2040Data.load_reading) {
          const loadMatch = rp2040Data.load_reading.match(/(\d+\.?\d*)/);
          if (loadMatch) {
            massG = parseFloat(loadMatch[1]);
          }
        }
      }

      // Update telemetry state
      setTelemetry({
        ts: Date.now(),
        rpm: rpm,
        tempC: tempC,
        massG: massG
      });

      // Update connection status
      const isConnected = (omronData?.status === 'connected') || (rp2040Data?.status === 'connected');
      setConnected(isConnected);

    } catch (error) {
      console.error('Failed to fetch telemetry data:', error);
      setConnected(false);
      
      // Keep last values but update timestamp
      setTelemetry(prev => ({
        ...prev,
        ts: Date.now()
      }));
    }
  };

  // Start periodic data fetching
  useEffect(() => {
    // Initial fetch
    fetchTelemetryData();

    // Set up interval for real-time updates
    intervalRef.current = setInterval(fetchTelemetryData, 1000); // 1Hz updates

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return { 
    telemetry, 
    connected,
    refreshTelemetry: fetchTelemetryData
  };
}