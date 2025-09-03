import { useState, useEffect } from 'react';

export function useTestConfig(configPath = '/config/test-profile.json') {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadConfig = async (path) => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(path);
      if (!response.ok) {
        throw new Error(`Failed to load config: ${response.status} - ${response.statusText}`);
      }
      const configData = await response.json();
      setConfig(configData);
    } catch (err) {
      setError(err.message);
      setConfig(null);
      console.error('Failed to load test config:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig(configPath);
  }, [configPath]);

  // Helper function to get interpolated value at specific time
  const getValueAtTime = (setpoints, currentTime) => {
    if (!setpoints || setpoints.length === 0) return 0;
    
    // Find the two points to interpolate between
    let beforePoint = setpoints[0];
    let afterPoint = setpoints[setpoints.length - 1];
    
    for (let i = 0; i < setpoints.length - 1; i++) {
      if (currentTime >= setpoints[i].time_sec && currentTime <= setpoints[i + 1].time_sec) {
        beforePoint = setpoints[i];
        afterPoint = setpoints[i + 1];
        break;
      }
    }
    
    // If current time is before first point, return first value
    if (currentTime <= setpoints[0].time_sec) {
      return setpoints[0].value;
    }
    
    // If current time is after last point, return last value
    if (currentTime >= setpoints[setpoints.length - 1].time_sec) {
      return setpoints[setpoints.length - 1].value;
    }
    
    // Linear interpolation
    const timeDiff = afterPoint.time_sec - beforePoint.time_sec;
    const valueDiff = afterPoint.value - beforePoint.value;
    const timeRatio = (currentTime - beforePoint.time_sec) / timeDiff;
    
    return beforePoint.value + (valueDiff * timeRatio);
  };

  // Convert setpoints to chart format with optional manual overrides
  const getChartData = (maxTime = 900, overrides = {}) => {
    if (!config) return { rpm: [], temperature: [] };
    
    const timeStep = 10; // 10 second intervals for chart
    const points = Math.ceil(maxTime / timeStep) + 1;
    
    const rpmData = [];
    const tempData = [];
    
    for (let i = 0; i < points; i++) {
      const time = i * timeStep;
      let rpmDesired = getValueAtTime(config.setpoints.rpm, time);
      let tempDesired = getValueAtTime(config.setpoints.temperature, time);
      
      // Apply manual overrides if provided
      if (overrides.manualRpm !== null && overrides.manualRpm !== undefined) {
        rpmDesired = overrides.manualRpm;
      }
      if (overrides.manualTemp !== null && overrides.manualTemp !== undefined) {
        tempDesired = overrides.manualTemp;
      }
      
      // Mock actual values with some deviation from desired
      const rpmActual = rpmDesired + (Math.random() - 0.5) * 100;
      const tempActual = tempDesired + (Math.random() - 0.5) * 5;
      
      rpmData.push({
        t: time,
        desired: rpmDesired,
        actual: rpmActual
      });
      
      tempData.push({
        t: time,
        desired: tempDesired,
        actual: tempActual
      });
    }
    
    return { rpm: rpmData, temperature: tempData };
  };

  return {
    config,
    loading,
    error,
    getValueAtTime,
    getChartData,
    loadConfig
  };
}