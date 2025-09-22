import { useState, useEffect } from 'react';

export function useWaveform() {
  const [waveformData, setWaveformData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastChannel, setLastChannel] = useState('CHAN1');
  const [lastFetch, setLastFetch] = useState(0);

  const fetchWaveform = async (channel = 'CHAN1', points = 1000) => {
    // Throttle requests to prevent MSO "query interrupted" - minimum 2 seconds between calls
    const now = Date.now();
    if (now - lastFetch < 2000) {
      console.log('Throttling waveform request - too soon after last call');
      return;
    }
    setLastFetch(now);
    
    setLoading(true);
    setError(null);
    setLastChannel(channel);
    
    try {
      const response = await fetch(`http://localhost:8000/api/scope/waveform?channel=${channel}&points=${points}`);
      
      if (!response.ok) {
        throw new Error(`Failed to fetch waveform: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      // Transform API data for Recharts
      const chartData = data.waveform.map(point => ({
        x: point.x * 1000, // Convert to milliseconds for better display
        y: point.y        // Voltage in volts
      }));
      
      setWaveformData({
        channel: data.channel,
        points: data.points_returned,
        sampleRate: data.sample_rate_hz,
        timeSpan: data.time_span_s,
        voltageRange: data.voltage_range_v,
        data: chartData,
        timestamp: data.timestamp,
        acquisitionInfo: data.acquisition_info
      });
      
    } catch (err) {
      console.error('Waveform fetch failed:', err);
      setError(err.message);
      
      // Fallback to mock data if API fails
      const mockData = Array.from({length: points/4}, (_, i) => ({
        x: i * 0.1, // 0.1ms steps
        y: channel === "CHAN1" ? Math.sin(i/20) + Math.random()*0.1 :
           channel === "CHAN2" ? Math.cos(i/15) * 0.5 + Math.random()*0.05 :
           channel === "CHAN3" ? Math.sin(i/25) * 1.2 + Math.random()*0.2 :
           Math.sin(i/40) * 0.3 + Math.random()*0.02
      }));
      
      setWaveformData({
        channel: channel,
        points: mockData.length,
        sampleRate: 50000,
        timeSpan: 0.025,
        voltageRange: [-1.5, 1.5],
        data: mockData,
        timestamp: new Date().toISOString(),
        acquisitionInfo: { mode: 'MOCK' }
      });
      
    } finally {
      setLoading(false);
    }
  };

  // No automatic fetching - MSO data is heavy and should only be fetched manually
  // useEffect removed to prevent any automatic API calls

  const refreshWaveform = (channel) => {
    fetchWaveform(channel || lastChannel);
  };

  return {
    waveformData,
    loading,
    error,
    refreshWaveform
  };
}