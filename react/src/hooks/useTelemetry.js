import { useState, useEffect, useRef } from 'react';

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState({
    ts: Date.now(), rpm: 0, tempC: 0, massG: 0,
  });
  const [connected, setConnected] = useState(false);
  const intervalRef = useRef(null);

  const fetchTelemetryData = async () => {
    try {
      // 1) Try new dedicated endpoint (new api_server)
      const r1 = await fetch('http://localhost:8000/api/telemetry');
      if (r1.ok) {
        const data = await r1.json();
        if (!data.detail) {  // "Not Found" returns {detail:...}
          setTelemetry({ ts: Date.now(), rpm: data.rpm ?? 0, tempC: data.tempC ?? 0, massG: data.massG ?? 0 });
          setConnected(true);
          return;
        }
      }
    } catch (_) {}

    try {
      // 2) Try live_telemetry from run/status (works if new api_server but no /api/telemetry yet)
      const r2 = await fetch('http://localhost:8000/api/run/status');
      if (r2.ok) {
        const run = await r2.json();
        if (run.state === 'running' && run.live_telemetry) {
          const t = run.live_telemetry;
          if (t.rpm_meas != null || t.omron_pv_c != null) {
            setTelemetry({ ts: Date.now(), rpm: t.rpm_meas ?? 0, tempC: t.omron_pv_c ?? 0, massG: 0 });
            setConnected(true);
            return;
          }
        }
      }
    } catch (_) {}

    try {
      // 3) Fallback: poll hardware endpoints directly (works when idle)
      const [omronR, rpR] = await Promise.all([
        fetch('http://localhost:8000/api/omron/status'),
        fetch('http://localhost:8000/api/rp2040/status'),
      ]);
      const omron = omronR.ok ? await omronR.json() : null;
      const rp    = rpR.ok   ? await rpR.json()    : null;

      let rpm = 0, tempC = 0, massG = 0;
      if (omron?.status === 'connected') tempC = omron.process_value_c ?? 0;
      if (rp?.status === 'connected') {
        const ms = rp.speed_reading?.match(/rpm=([\d.]+)/);
        const ml = rp.load_reading?.match(/mass_g=([\d.]+)/);
        if (ms) rpm   = parseFloat(ms[1]);
        if (ml) massG = parseFloat(ml[1]);
      }
      setTelemetry({ ts: Date.now(), rpm, tempC, massG });
      setConnected(omron?.status === 'connected' || rp?.status === 'connected');
    } catch (e) {
      console.error('Telemetry fetch failed:', e);
      setConnected(false);
    }
  };

  useEffect(() => {
    fetchTelemetryData();
    intervalRef.current = setInterval(fetchTelemetryData, 1000);
    return () => clearInterval(intervalRef.current);
  }, []);

  return { telemetry, connected, refreshTelemetry: fetchTelemetryData };
}
