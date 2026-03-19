import { useState, useEffect, useRef } from 'react';

const API = 'http://localhost:8000';

export function useHDF5Status() {
  const [fileInfo, setFileInfo] = useState({
    filename: null,
    created: null,
    isActive: false,
    currentSizeBytes: 0,
    maxSizeBytes: 0,        // actual disk free space
    diskFreeBytes: 0,
    diskTotalBytes: 0,
    totalSamples: 0,
    maxSamples: 0,
    totalSweeps: 0,
    activeChannels: 0,
    recordingDuration: 0,
  });

  const intervalRef = useRef(null);

  const fetchStatus = async () => {
    try {
      const r = await fetch(`${API}/api/hdf5/status`);
      if (!r.ok) return;
      const data = await r.json();
      setFileInfo(prev => ({
        ...prev,
        filename:          data.filename          ?? prev.filename,
        created:           data.created           ?? prev.created,
        isActive:          data.isActive          ?? false,
        currentSizeBytes:  data.currentSizeBytes  ?? 0,
        diskFreeBytes:     data.diskFreeBytes      ?? prev.diskFreeBytes,
        diskTotalBytes:    data.diskTotalBytes     ?? prev.diskTotalBytes,
        // maxSizeBytes = current file size + free space (total usable for this file)
        maxSizeBytes:      (data.currentSizeBytes ?? 0) + (data.diskFreeBytes ?? 0),
        totalSweeps:       data.totalSweeps       ?? 0,
        totalSamples:      data.totalSamples      ?? 0,
        activeChannels:    data.activeChannels     ?? prev.activeChannels,
        recordingDuration: data.recordingDuration  ?? 0,
      }));
    } catch (e) {
      console.error('HDF5 status fetch failed:', e);
    }
  };

  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 2000);
    return () => clearInterval(intervalRef.current);
  }, []);

  const startRecording = () => setTimeout(fetchStatus, 500);
  const stopRecording  = () => setTimeout(fetchStatus, 500);
  const resetFile      = () => setTimeout(fetchStatus, 500);

  return { fileInfo, startRecording, stopRecording, resetFile };
}
