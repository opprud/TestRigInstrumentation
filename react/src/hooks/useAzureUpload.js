import { useState, useRef, useCallback, useEffect } from "react";

const API_BASE = "http://localhost:8000";

/**
 * Hook for uploading HDF5 files to Azure Blob Storage with progress tracking.
 *
 * Usage:
 *   const { upload, status, progress, reset } = useAzureUpload();
 *   await upload({ container: "data" });
 */
export function useAzureUpload() {
  const [state, setState] = useState({
    status: "idle",       // idle | uploading | done | error
    filename: null,
    container: null,
    bytesSent: 0,
    bytesTotal: 0,
    percent: 0,
    error: null,
    blobUrl: null,
  });

  const pollRef = useRef(null);

  // Poll upload progress from backend
  const startPolling = useCallback(() => {
    if (pollRef.current) return;

    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/api/azure/upload/status`);
        if (!r.ok) return;
        const data = await r.json();

        setState({
          status: data.status,
          filename: data.filename,
          container: data.container,
          bytesSent: data.bytes_sent || 0,
          bytesTotal: data.bytes_total || 0,
          percent: data.percent || 0,
          error: data.error,
          blobUrl: data.blob_url,
        });

        // Stop polling when done or error
        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (e) {
        // ignore poll errors
      }
    }, 500);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  // Start upload
  const upload = useCallback(async ({ container = "data", blobName = null, filePath = null } = {}) => {
    setState(prev => ({
      ...prev,
      status: "uploading",
      percent: 0,
      bytesSent: 0,
      error: null,
      blobUrl: null,
    }));

    try {
      const r = await fetch(`${API_BASE}/api/azure/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container,
          blob_name: blobName,
          file_path: filePath,
        }),
      });

      if (!r.ok) {
        const text = await r.text().catch(() => "");
        let detail = text;
        try { detail = JSON.parse(text).detail; } catch (e) { /* ignore */ }
        throw new Error(detail || `Upload failed (${r.status})`);
      }

      const data = await r.json();
      setState(prev => ({
        ...prev,
        filename: data.file,
        container: data.container,
      }));

      // Start polling for progress
      startPolling();
      return data;

    } catch (e) {
      setState(prev => ({
        ...prev,
        status: "error",
        error: e.message || String(e),
      }));
      throw e;
    }
  }, [startPolling]);

  // Fetch available containers
  const fetchContainers = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/azure/containers`);
      if (!r.ok) return [];
      const data = await r.json();
      return data.containers || [];
    } catch (e) {
      return [];
    }
  }, []);

  // Fetch available HDF5 files
  const fetchFiles = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/azure/files`);
      if (!r.ok) return [];
      const data = await r.json();
      return data.files || [];
    } catch (e) {
      return [];
    }
  }, []);

  // Cancel an in-progress upload
  const cancel = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/azure/upload/cancel`, { method: "POST" });
    } catch (e) {
      // ignore
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setState(prev => ({ ...prev, status: "cancelled" }));
  }, []);

  // Reset state
  const reset = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setState({
      status: "idle",
      filename: null,
      container: null,
      bytesSent: 0,
      bytesTotal: 0,
      percent: 0,
      error: null,
      blobUrl: null,
    });
  }, []);

  return {
    ...state,
    upload,
    cancel,
    reset,
    fetchContainers,
    fetchFiles,
    isUploading: state.status === "uploading",
    isDone: state.status === "done",
    isError: state.status === "error",
    isCancelled: state.status === "cancelled",
  };
}
