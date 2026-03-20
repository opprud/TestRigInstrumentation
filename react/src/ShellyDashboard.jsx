import React, { useState, useEffect, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Zap, Thermometer, Activity, Wifi, WifiOff, RefreshCw } from "lucide-react";

const API = "http://localhost:8000";

function formatPower(w) {
  if (w == null) return "—";
  return `${w.toFixed(1)} W`;
}
function formatCurrent(a) {
  if (a == null) return "—";
  return `${(a * 1000).toFixed(0)} mA`;
}
function formatVoltage(v) {
  if (v == null) return "—";
  return `${v.toFixed(1)} V`;
}
function formatEnergy(wh) {
  if (wh == null) return "—";
  if (wh >= 1000) return `${(wh / 1000).toFixed(2)} kWh`;
  return `${wh.toFixed(1)} Wh`;
}

function ChannelCard({ channel, onToggle, toggling }) {
  const isOn = channel.output === true;
  const isUnknown = channel.output == null;

  return (
    <div
      className={`
        relative rounded-2xl border-2 transition-all duration-300 overflow-hidden
        ${isOn
          ? "border-emerald-400 bg-emerald-950/40 shadow-lg shadow-emerald-900/30"
          : isUnknown
            ? "border-zinc-700 bg-zinc-900/40"
            : "border-zinc-700 bg-zinc-900/40"
        }
      `}
    >
      {/* Top bar with name and toggle */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3">
        <div>
          <div className="text-base font-semibold text-zinc-100 tracking-tight">
            {channel.name}
          </div>
          {channel.description && (
            <div className="text-xs text-zinc-500 mt-0.5">{channel.description}</div>
          )}
        </div>

        {/* Toggle button */}
        <button
          onClick={() => onToggle(channel.id, !isOn)}
          disabled={toggling || !channel.enabled}
          className={`
            relative w-14 h-7 rounded-full transition-all duration-300 focus:outline-none
            ${isOn ? "bg-emerald-500" : "bg-zinc-700"}
            ${toggling ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:brightness-110"}
          `}
        >
          <span
            className={`
              absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-all duration-300
              ${isOn ? "left-7" : "left-0.5"}
            `}
          />
        </button>
      </div>

      {/* Status badge */}
      <div className="px-5 pb-3">
        <span className={`
          inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full
          ${isOn ? "bg-emerald-500/20 text-emerald-300" : isUnknown ? "bg-zinc-800 text-zinc-500" : "bg-zinc-800 text-zinc-400"}
        `}>
          <span className={`w-1.5 h-1.5 rounded-full ${isOn ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"}`} />
          {isUnknown ? "Unknown" : isOn ? "ON" : "OFF"}
        </span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-px bg-zinc-800/50 border-t border-zinc-800">
        {[
          { label: "Power", value: formatPower(channel.apower), icon: Zap, active: isOn },
          { label: "Current", value: formatCurrent(channel.current), icon: Activity, active: isOn },
          { label: "Voltage", value: formatVoltage(channel.voltage), icon: Activity, active: true },
          { label: "Energy", value: formatEnergy(channel.aenergy_total), icon: Zap, active: true },
        ].map((metric) => (
          <div key={metric.label} className="px-4 py-3 bg-zinc-900/60">
            <div className="text-xs text-zinc-500 mb-1">{metric.label}</div>
            <div className={`text-sm font-mono font-medium ${metric.active && isOn ? "text-emerald-300" : "text-zinc-400"}`}>
              {metric.value}
            </div>
          </div>
        ))}
      </div>

      {/* Temperature if available */}
      {channel.temperature_c != null && (
        <div className="flex items-center gap-2 px-5 py-2.5 border-t border-zinc-800 bg-zinc-900/40">
          <Thermometer className="h-3.5 w-3.5 text-orange-400" />
          <span className="text-xs text-zinc-400">Device temp:</span>
          <span className="text-xs font-mono text-orange-300">{channel.temperature_c.toFixed(1)}°C</span>
        </div>
      )}
    </div>
  );
}

export default function ShellyDashboard() {
  const [status, setStatus] = useState(null);
  const [toggling, setToggling] = useState({});
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchStatus = async () => {
    try {
      const r = await fetch(`${API}/api/shelly/status`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setStatus(data);
      setLastUpdate(new Date());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 2000);
    return () => clearInterval(intervalRef.current);
  }, []);

  const handleToggle = async (channelId, on) => {
    setToggling(prev => ({ ...prev, [channelId]: true }));
    try {
      const r = await fetch(`${API}/api/shelly/switch/${channelId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ on }),
      });
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        setLastUpdate(new Date());
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setToggling(prev => ({ ...prev, [channelId]: false }));
    }
  };

  const connected = status?.connected ?? false;
  const channels = status?.channels ?? [];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-zinc-100">
              Power Control
            </h1>
            <p className="text-xs text-zinc-500 mt-0.5">Shelly Pro 4PM</p>
          </div>

          <div className="flex items-center gap-3">
            {lastUpdate && (
              <span className="text-xs text-zinc-600">
                {lastUpdate.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={fetchStatus}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
              ${connected ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
              {connected
                ? <><Wifi className="h-3.5 w-3.5" /> Connected</>
                : <><WifiOff className="h-3.5 w-3.5" /> Offline</>
              }
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 px-4 py-3 rounded-xl bg-red-950/50 border border-red-800 text-red-300 text-sm">
            ⚠️ {error}
          </div>
        )}

        {!status ? (
          <div className="flex items-center justify-center h-64 text-zinc-600 text-sm">
            Connecting to Shelly...
          </div>
        ) : (
          <>
            {/* Active power summary */}
            {channels.some(c => c.output && c.apower) && (
              <div className="mb-6 px-5 py-4 rounded-2xl bg-zinc-900 border border-zinc-800">
                <div className="text-xs text-zinc-500 mb-1">Total Active Power</div>
                <div className="text-2xl font-mono font-bold text-emerald-400">
                  {channels.reduce((sum, c) => sum + (c.output ? (c.apower ?? 0) : 0), 0).toFixed(1)} W
                </div>
              </div>
            )}

            {/* Channel grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {channels.map(channel => (
                <ChannelCard
                  key={channel.id}
                  channel={channel}
                  onToggle={handleToggle}
                  toggling={toggling[channel.id] ?? false}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
