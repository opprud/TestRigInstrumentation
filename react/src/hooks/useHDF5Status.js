import { useState, useEffect } from 'react';

export function useHDF5Status() {
  const [fileInfo, setFileInfo] = useState({
    filename: 'data_20241201_143022.h5',
    created: '2024-12-01 14:30:22',
    isActive: false,
    currentSizeBytes: 0,
    maxSizeBytes: 500 * 1024 * 1024, // 500MB limit
    totalSamples: 0,
    maxSamples: 100000, // 100k sample limit
    totalSweeps: 0,
    activeChannels: 4,
    recordingDuration: 0, // seconds
  });

  const [startTime, setStartTime] = useState(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setFileInfo(prev => {
        // Simulate data growth when recording is active
        if (prev.isActive) {
          const now = Date.now();
          const elapsedSeconds = startTime ? Math.floor((now - startTime) / 1000) : 0;
          
          // Simulate file growth: ~1MB per minute when recording
          const growthRate = 1024 * 1024 / 60; // bytes per second
          const newSize = Math.min(
            prev.currentSizeBytes + growthRate,
            prev.maxSizeBytes
          );

          // Simulate sample accumulation: ~10 samples per second
          const sampleGrowthRate = 10;
          const newSamples = Math.min(
            prev.totalSamples + sampleGrowthRate,
            prev.maxSamples
          );

          // Increment sweep count every 30 seconds when recording
          const newSweeps = prev.totalSweeps + (elapsedSeconds % 30 === 0 && elapsedSeconds > 0 ? 1 : 0);

          return {
            ...prev,
            currentSizeBytes: newSize,
            totalSamples: newSamples,
            totalSweeps: newSweeps,
            recordingDuration: elapsedSeconds,
          };
        }
        return prev;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime]);

  const startRecording = () => {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, -5);
    
    setFileInfo(prev => ({
      ...prev,
      filename: `data_${timestamp}.h5`,
      created: now.toLocaleString(),
      isActive: true,
      currentSizeBytes: 1024, // Start with 1KB header
      totalSamples: 0,
      totalSweeps: 0,
      recordingDuration: 0,
    }));
    
    setStartTime(Date.now());
  };

  const stopRecording = () => {
    setFileInfo(prev => ({
      ...prev,
      isActive: false,
    }));
    setStartTime(null);
  };

  const resetFile = () => {
    const now = new Date();
    const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, -5);
    
    setFileInfo(prev => ({
      ...prev,
      filename: `data_${timestamp}.h5`,
      created: now.toLocaleString(),
      isActive: false,
      currentSizeBytes: 0,
      totalSamples: 0,
      totalSweeps: 0,
      recordingDuration: 0,
    }));
    setStartTime(null);
  };

  return {
    fileInfo,
    startRecording,
    stopRecording,
    resetFile,
  };
}