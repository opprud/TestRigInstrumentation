import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTestConfig } from "./hooks/useTestConfig";
import { useHDF5Status } from "./hooks/useHDF5Status";
import { useHardwareStatus } from "./hooks/useHardwareStatus";
import { useTelemetry } from "./hooks/useTelemetry";
import { useWaveform } from "./hooks/useWaveform";
import { ConfigSelector } from "./components/ConfigSelector";
import { HDF5Status } from "./components/HDF5Status";
import { HardwareStatus } from "./components/HardwareStatus";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { Play, Square, Radio, ThermometerSun, Gauge, HardDriveDownload, Cpu, Link as LinkIcon, FileText, Activity, RefreshCw } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip as RTooltip, CartesianGrid, ResponsiveContainer, ReferenceLine, AreaChart, Area } from "recharts";
import { motion } from "framer-motion";

// --- Mock WebSocket hook (replace with real backend) ---
function useMockTelemetry() {
  const [telemetry, setTelemetry] = useState({ ts: Date.now(), rpm: 0, tempC: 0, massG: 0 });
  const [connected, setConnected] = useState(true);
  const ref = useRef({ t: 0, dir: 1 });

  useEffect(() => {
    const id = setInterval(() => {
      // simple evolving mock
      ref.current.t += 1 * ref.current.dir;
      if (ref.current.t > 200) ref.current.dir = -1;
      if (ref.current.t < 0) ref.current.dir = 1;
      const now = Date.now();
      setTelemetry({
        ts: now,
        rpm: 1200 + 400 * Math.sin(ref.current.t / 12),
        tempC: 40 + 10 * Math.sin(ref.current.t / 30),
        massG: 200 + 50 * Math.sin(ref.current.t / 20),
      });
    }, 500);
    return () => clearInterval(id);
  }, []);

  return { telemetry, connected };
}

// --- Small helper components ---
function Stat({ icon: Icon, label, value, unit, colorRing }) {
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="p-4 flex items-center gap-4">
        <div className="relative">
          <div className={`absolute inset-0 rounded-full blur-md opacity-40 ${colorRing}`} />
          <div className="h-10 w-10 rounded-full bg-white/70 flex items-center justify-center shadow">
            <Icon className="h-5 w-5" />
          </div>
        </div>
        <div className="flex-1">
          <div className="text-sm text-muted-foreground">{label}</div>
          <div className="text-2xl font-semibold tracking-tight">
            {value}
            {unit && <span className="text-sm font-normal text-muted-foreground"> {unit}</span>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-lg font-semibold tracking-tight">{children}</h3>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

// --- Timeline (desired vs actual) ---
function SetpointChart({ data, desiredKey = "desired", actualKey = "actual", yLabel = "Value" }) {
  // Smart time formatting based on duration
  const formatTime = (seconds) => {
    if (seconds >= 3600) { // >= 1 hour
      return `${(seconds / 3600).toFixed(1)}h`;
    } else if (seconds >= 60) { // >= 1 minute  
      return `${(seconds / 60).toFixed(0)}m`;
    } else {
      return `${seconds}s`;
    }
  };

  return (
    <div className="h-40">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="t" 
            tickFormatter={formatTime} 
            interval="preserveStartEnd" 
          />
          <YAxis width={50} />
          <RTooltip 
            formatter={(v) => v.toFixed ? v.toFixed(2) : v} 
            labelFormatter={(v) => `Time: ${formatTime(v)}`} 
          />
          <Line type="monotone" dataKey={desiredKey} strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey={actualKey} strokeWidth={2} strokeDasharray="4 2" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}


// --- Main App ---
export default function Dashboard() {
  const { telemetry, connected } = useTelemetry();
  const [runState, setRunState] = useState("stopped"); // "stopped" | "running"
  const [planEnabled, setPlanEnabled] = useState(true);
  
  // Manual override controls
  const [manualRpm, setManualRpm] = useState(1500);
  const [manualTemp, setManualTemp] = useState(60);
  const [previewChannel, setPreviewChannel] = useState("CHAN1");
  
  // Load test configuration from JSON file
  const { config, loading: configLoading, error: configError, getChartData, getTestDuration, loadConfig } = useTestConfig();
  
  // HDF5 file status
  const { fileInfo, startRecording, stopRecording, resetFile } = useHDF5Status();
  
  // Hardware connection status
  const { hardwareInfo, isScanning, scanHardware } = useHardwareStatus();

  // Waveform data from oscilloscope
  const { waveformData, loading: waveformLoading, error: waveformError, refreshWaveform } = useWaveform();

  // Note: Waveform data is now fetched manually only (via refresh button)
  // No auto-refresh to avoid heavy MSO-X data acquisition

  // Get timeline data from config with manual overrides
  const { rpm: rpmTimeline, temperature: tempTimeline } = useMemo(() => {
    if (configLoading || configError || !config) {
      // Fallback to original mock data if config not available
      const rpmFallback = Array.from({ length: 31 }, (_, i) => ({
        t: i * 10,
        desired: i < 10 ? 1000 : i < 20 ? 1500 : 2000,
        actual: i < 5 ? 900 + i*20 : 1400 + (i-10)*10,
      }));
      const tempFallback = Array.from({ length: 31 }, (_, i) => ({
        t: i * 10,
        desired: i < 12 ? 40 : i < 24 ? 60 : 80,
        actual: i < 6 ? 35 + i : 58 + (i-12)*0.8,
      }));
      return { rpm: rpmFallback, temperature: tempFallback };
    }
    
    // Apply manual overrides if not using plan
    const overrides = {};
    if (!planEnabled) {
      overrides.manualRpm = manualRpm;
      overrides.manualTemp = manualTemp;
    }
    
    return getChartData(null, overrides); // Use actual test duration from config
  }, [config, configLoading, configError, getChartData, planEnabled, manualRpm, manualTemp]);

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
        {/* Top bar */}
        <div className="sticky top-0 z-20 border-b bg-white/70 backdrop-blur supports-[backdrop-filter]:bg-white/60">
          <div className="mx-auto max-w-7xl px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Cpu className="h-5 w-5" />
              <div>
                <div className="font-semibold">Experiment Dashboard</div>
                <div className="text-xs text-muted-foreground">
                  {config ? config.name : 'MSO-X 2024A · RP2040 · E5CC'}
                  {configLoading && ' · Loading config...'}
                  {configError && ' · Config error'}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <HardwareStatus hardwareInfo={hardwareInfo} />
              <Badge variant={configError ? "destructive" : config ? "default" : "secondary"} className="gap-1">
                <FileText className="h-3.5 w-3.5" /> 
                {configLoading ? "Loading..." : configError ? "Config Error" : config ? "Profile Loaded" : "No Config"}
              </Badge>
              {runState === "running" ? (
                <Button onClick={() => {
                  setRunState("stopped");
                  stopRecording();
                }} variant="destructive" className="gap-2"><Square className="h-4 w-4"/>Stop</Button>
              ) : (
                <Button onClick={() => {
                  setRunState("running");
                  startRecording();
                }} className="gap-2"><Play className="h-4 w-4"/>Start</Button>
              )}
            </div>
          </div>
        </div>

        <main className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-12 gap-4">
          {/* Left column: live stats + controls */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <SectionTitle right={
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="gap-1">
                  <Activity className="h-3 w-3"/> Live
                </Badge>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={scanHardware} 
                  disabled={isScanning}
                  className="gap-1 text-xs h-6"
                >
                  {isScanning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                  Scan
                </Button>
              </div>
            }>
              Live Telemetry
            </SectionTitle>
            <div className="grid grid-cols-2 gap-3">
              <Stat icon={Gauge} label="Speed" value={telemetry.rpm.toFixed(0)} unit="rpm" colorRing="bg-emerald-200"/>
              <Stat icon={ThermometerSun} label="Temperature" value={telemetry.tempC.toFixed(1)} unit="°C" colorRing="bg-amber-200"/>
              <Stat icon={Radio} label="Load" value={telemetry.massG.toFixed(1)} unit="g" colorRing="bg-sky-200"/>
              <Stat icon={FileText} label="Last sweep" value={`#${fileInfo.totalSweeps.toString().padStart(3, '0')}`} unit="" colorRing="bg-rose-200"/>
            </div>

            <HDF5Status fileInfo={fileInfo} />

            <Card>
              <CardContent className="p-4 space-y-4">
                <ConfigSelector 
                  currentConfig={config}
                  onConfigChange={loadConfig}
                  loading={configLoading}
                />
                <Separator />
                <SectionTitle>Test Controls</SectionTitle>
                <div className="grid grid-cols-2 gap-3 items-center">
                  <Label htmlFor="plan" className="flex items-center gap-2">
                    Use Plan
                    {config && <Badge variant="outline" className="text-xs">Config</Badge>}
                  </Label>
                  <div className="flex items-center justify-end gap-2">
                    <Switch id="plan" checked={planEnabled} onCheckedChange={setPlanEnabled} />
                  </div>
                  
                  <Label htmlFor="rpm" className={planEnabled ? "text-muted-foreground" : ""}>
                    Manual RPM
                  </Label>
                  <div className="flex items-center gap-2">
                    <Slider 
                      id="rpm" 
                      value={[manualRpm]} 
                      onValueChange={(value) => setManualRpm(value[0])}
                      max={3000} 
                      min={500}
                      step={50} 
                      className="w-full" 
                      disabled={planEnabled}
                    />
                    <Input 
                      className="w-20" 
                      value={manualRpm}
                      onChange={(e) => setManualRpm(Number(e.target.value))}
                      disabled={planEnabled}
                    />
                  </div>
                  
                  <Label htmlFor="temp" className={planEnabled ? "text-muted-foreground" : ""}>
                    Manual Temp
                  </Label>
                  <div className="flex items-center gap-2">
                    <Slider 
                      id="temp" 
                      value={[manualTemp]} 
                      onValueChange={(value) => setManualTemp(value[0])}
                      max={120} 
                      min={20}
                      step={5} 
                      className="w-full"
                      disabled={planEnabled}
                    />
                    <Input 
                      className="w-20" 
                      value={manualTemp}
                      onChange={(e) => setManualTemp(Number(e.target.value))}
                      disabled={planEnabled}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2 justify-end">
                  <Button variant="outline" size="sm" onClick={resetFile} className="gap-1">
                    <HardDriveDownload className="h-3 w-3"/> New File
                  </Button>
                  <Button variant="secondary" className="gap-2"><HardDriveDownload className="h-4 w-4"/> Save Config</Button>
                  <Button className="gap-2"><Play className="h-4 w-4"/> Apply</Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right column: trends + sweeps */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <Card>
              <CardContent className="p-4 space-y-3">
                <SectionTitle>
                  Setpoints: RPM
                  {config && <Badge variant="outline" className="text-xs">Config Profile</Badge>}
                  {!planEnabled && <Badge variant="destructive" className="text-xs">Manual Override</Badge>}
                </SectionTitle>
                <SetpointChart data={rpmTimeline} yLabel="rpm" desiredKey="desired" actualKey="actual" />
                <Separator />
                <SectionTitle>
                  Setpoints: Temperature
                  {config && <Badge variant="outline" className="text-xs">Config Profile</Badge>}
                  {!planEnabled && <Badge variant="destructive" className="text-xs">Manual Override</Badge>}
                </SectionTitle>
                <SetpointChart data={tempTimeline} yLabel="°C" desiredKey="desired" actualKey="actual" />
              </CardContent>
            </Card>


            <Card>
              <CardContent className="p-4">
                <SectionTitle right={
                  <div className="flex items-center gap-2">
                    <Label className="text-xs">Channel:</Label>
                    <select 
                      value={previewChannel}
                      onChange={(e) => setPreviewChannel(e.target.value)}
                      className="text-xs border rounded px-2 py-1 bg-background"
                    >
                      <option value="CHAN1">CH1 - AE</option>
                      <option value="CHAN2">CH2 - Accel</option>
                      <option value="CHAN3">CH3 - UL</option>
                      <option value="CHAN4">CH4 - Temp</option>
                    </select>
                  </div>
                }>
                  Waveform Preview ({previewChannel})
                </SectionTitle>
                <div className="h-48 relative">
                  {waveformLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
                      <div className="text-sm text-muted-foreground">Loading waveform...</div>
                    </div>
                  )}
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={waveformData?.data || []}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="x" 
                        tickFormatter={(v) => `${v.toFixed(1)}ms`} 
                        label={{ value: 'Time (ms)', position: 'insideBottom', offset: -5 }}
                      />
                      <YAxis 
                        tickFormatter={(v) => `${v.toFixed(3)}V`}
                        label={{ value: 'Voltage (V)', angle: -90, position: 'insideLeft' }}
                      />
                      <RTooltip 
                        formatter={(v) => [`${v.toFixed(4)}V`, previewChannel]} 
                        labelFormatter={(v) => `Time: ${v.toFixed(2)}ms`} 
                      />
                      <Line 
                        type="monotone" 
                        dataKey="y" 
                        dot={false} 
                        strokeWidth={2}
                        stroke={
                          previewChannel === "CHAN1" ? "#eab308" : // yellow
                          previewChannel === "CHAN2" ? "#22c55e" : // green  
                          previewChannel === "CHAN3" ? "#3b82f6" : // blue
                          "#ef4444" // red
                        }
                      />
                      <ReferenceLine y={0} strokeDasharray="3 3" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="text-xs text-muted-foreground mt-2 flex justify-between items-center">
                  <div>
                    {waveformError ? (
                      <span className="text-destructive">⚠️ {waveformError}</span>
                    ) : waveformData ? (
                      <span>
                        📡 {waveformData.channel} data: {waveformData.points} pts, {Math.round(waveformData.sampleRate/1000)}kHz
                        {waveformData.acquisitionInfo?.mode === 'MOCK' && ' (mock)'}
                      </span>
                    ) : (
                      <span>Click refresh to capture waveform from {previewChannel}</span>
                    )}
                  </div>
                  <button 
                    onClick={() => refreshWaveform(previewChannel)}
                    className="text-xs hover:text-foreground transition-colors bg-secondary/50 hover:bg-secondary px-2 py-1 rounded"
                    disabled={waveformLoading}
                  >
                    {waveformLoading ? '⏳ Capturing...' : '🔄 Capture'}
                  </button>
                </div>
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </TooltipProvider>
  );
}

/*
Integration guide:
- Replace useMockTelemetry with a real WebSocket (or SSE) to your FastAPI backend.
  ws message example:
    {
      type: "telemetry",
      ts_ms: 1723999999999,
      rpm: 1523.2,
      tempC: 62.1,
      massG: 201.4
    }
- Expose endpoints:
    POST /api/run/start   { planEnabled, manualOverrides }
    POST /api/run/stop
    GET  /api/run/status  -> { state, currentStep, filePath, sweepCount }
    GET  /api/streams/speed?since=... -> downsample for charts
    GET  /api/streams/temp?since=...
    GET  /api/sweeps/recent -> list with small thumbnails (server can precompute PNGs)
- Use the Controls section to either enable plan tracking or set manual RPM/Temp.
- The Setpoint charts should overlay desired vs actual using your HDF5 setpoints tables.
*/
