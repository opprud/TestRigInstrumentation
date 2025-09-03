import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Database, HardDrive, FileText, Clock, Zap } from "lucide-react";

export function HDF5Status({ fileInfo, className }) {
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  const getStorageProgress = () => {
    if (!fileInfo.maxSizeBytes || fileInfo.maxSizeBytes === 0) return 0;
    return (fileInfo.currentSizeBytes / fileInfo.maxSizeBytes) * 100;
  };

  const getSampleProgress = () => {
    if (!fileInfo.maxSamples || fileInfo.maxSamples === 0) return 0;
    return (fileInfo.totalSamples / fileInfo.maxSamples) * 100;
  };

  const storageProgress = getStorageProgress();
  const sampleProgress = getSampleProgress();
  const isNearFull = storageProgress > 80 || sampleProgress > 80;

  return (
    <Card className={className}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            <span className="text-sm font-medium">HDF5 Data Log</span>
          </div>
          <Badge variant={fileInfo.isActive ? "default" : "secondary"} className="gap-1">
            <Zap className="h-3 w-3" />
            {fileInfo.isActive ? "Recording" : "Idle"}
          </Badge>
        </div>

        <div className="text-xs text-muted-foreground">
          <div className="flex items-center gap-1 mb-1">
            <FileText className="h-3 w-3" />
            {fileInfo.filename || "No file"}
          </div>
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Created: {fileInfo.created || "N/A"}
          </div>
        </div>

        {/* Storage Usage */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1">
              <HardDrive className="h-3 w-3" />
              Storage
            </span>
            <span className={isNearFull && storageProgress > 80 ? "text-orange-600" : ""}>
              {formatFileSize(fileInfo.currentSizeBytes)} / {formatFileSize(fileInfo.maxSizeBytes)}
            </span>
          </div>
          <Progress 
            value={storageProgress} 
            className="h-2"
            indicatorClassName={storageProgress > 90 ? "bg-red-500" : storageProgress > 80 ? "bg-orange-500" : "bg-blue-500"}
          />
        </div>

        {/* Sample Count */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span>Samples</span>
            <span className={isNearFull && sampleProgress > 80 ? "text-orange-600" : ""}>
              {fileInfo.totalSamples?.toLocaleString()} / {fileInfo.maxSamples?.toLocaleString()}
            </span>
          </div>
          <Progress 
            value={sampleProgress} 
            className="h-2"
            indicatorClassName={sampleProgress > 90 ? "bg-red-500" : sampleProgress > 80 ? "bg-orange-500" : "bg-green-500"}
          />
        </div>

        {/* Sweep Info */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <div className="text-muted-foreground">Sweeps</div>
            <div className="font-medium">{fileInfo.totalSweeps || 0}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Channels</div>
            <div className="font-medium">{fileInfo.activeChannels || 0}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Duration</div>
            <div className="font-medium">{formatDuration(fileInfo.recordingDuration || 0)}</div>
          </div>
        </div>

        {/* Warnings */}
        {isNearFull && (
          <div className="text-xs text-orange-600 bg-orange-50 p-2 rounded border">
            ⚠️ Storage approaching limit. Consider starting new file or increasing limits.
          </div>
        )}
      </CardContent>
    </Card>
  );
}