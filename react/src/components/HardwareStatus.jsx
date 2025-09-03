import React from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { 
  Wifi, 
  WifiOff, 
  Cpu, 
  CpuIcon,
  Thermometer,
  Radio,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock
} from "lucide-react";

export function HardwareStatus({ hardwareInfo, className }) {
  const getStatusIcon = (status, connectedIcon = CheckCircle, disconnectedIcon = XCircle) => {
    switch (status) {
      case 'connected':
        return connectedIcon;
      case 'connecting':
        return Clock;
      case 'error':
        return AlertTriangle;
      default:
        return disconnectedIcon;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected':
        return 'default'; // green
      case 'connecting':
        return 'secondary'; // gray
      case 'error':
        return 'destructive'; // red
      default:
        return 'outline'; // outline
    }
  };

  const getStatusText = (status, deviceName) => {
    switch (status) {
      case 'connected':
        return `${deviceName} Connected`;
      case 'connecting':
        return `Connecting to ${deviceName}...`;
      case 'error':
        return `${deviceName} Error`;
      default:
        return `${deviceName} Offline`;
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* MSO-X 2024A Oscilloscope */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant={getStatusColor(hardwareInfo.scope.status)} 
            className="gap-1 cursor-pointer"
          >
            <Radio className="h-3 w-3" />
            MSO-X
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <div className="text-xs">
            <div className="font-medium">Keysight MSO-X 2024A</div>
            <div>Status: {getStatusText(hardwareInfo.scope.status, 'Oscilloscope')}</div>
            {hardwareInfo.scope.ip && (
              <div>IP: {hardwareInfo.scope.ip}</div>
            )}
            {hardwareInfo.scope.lastSeen && (
              <div>Last Seen: {hardwareInfo.scope.lastSeen}</div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>

      {/* RP2040 Microcontroller */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant={getStatusColor(hardwareInfo.rp2040.status)} 
            className="gap-1 cursor-pointer"
          >
            <Cpu className="h-3 w-3" />
            RP2040
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <div className="text-xs">
            <div className="font-medium">Seeed XIAO RP2040</div>
            <div>Status: {getStatusText(hardwareInfo.rp2040.status, 'Microcontroller')}</div>
            {hardwareInfo.rp2040.port && (
              <div>Port: {hardwareInfo.rp2040.port}</div>
            )}
            {hardwareInfo.rp2040.firmware && (
              <div>Firmware: {hardwareInfo.rp2040.firmware}</div>
            )}
            {hardwareInfo.rp2040.lastPing && (
              <div>Last Response: {hardwareInfo.rp2040.lastPing}</div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>

      {/* RS485/Modbus (Temperature Controller) */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant={getStatusColor(hardwareInfo.rs485.status)} 
            className="gap-1 cursor-pointer"
          >
            <Thermometer className="h-3 w-3" />
            E5CC
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <div className="text-xs">
            <div className="font-medium">Omron E5CC (RS485)</div>
            <div>Status: {getStatusText(hardwareInfo.rs485.status, 'Temperature Controller')}</div>
            {hardwareInfo.rs485.port && (
              <div>Port: {hardwareInfo.rs485.port}</div>
            )}
            {hardwareInfo.rs485.slaveId && (
              <div>Slave ID: {hardwareInfo.rs485.slaveId}</div>
            )}
            {hardwareInfo.rs485.lastRead && (
              <div>Last Read: {hardwareInfo.rs485.lastRead}</div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>

      {/* Overall System Status */}
      {hardwareInfo.scope.status === 'connected' && 
       hardwareInfo.rp2040.status === 'connected' && 
       hardwareInfo.rs485.status === 'connected' && (
        <Badge variant="default" className="gap-1">
          <CheckCircle className="h-3 w-3" />
          All Systems
        </Badge>
      )}
    </div>
  );
}