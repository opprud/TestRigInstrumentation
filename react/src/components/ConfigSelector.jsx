import React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileText, RefreshCw, FolderOpen } from "lucide-react";

const CONFIG_OPTIONS = [
  { path: '/config/test-profile.json', name: 'Standard Test' },
  { path: '/config/high-stress-profile.json', name: 'High Stress' },
  { path: 'custom', name: 'Custom Path...' },
];

export function ConfigSelector({ currentConfig, onConfigChange, loading }) {
  const [selectedOption, setSelectedOption] = React.useState(CONFIG_OPTIONS[0].path);
  const [customPath, setCustomPath] = React.useState('');

  const handleLoadConfig = () => {
    const pathToLoad = selectedOption === 'custom' ? customPath : selectedOption;
    if (pathToLoad.trim()) {
      onConfigChange(pathToLoad);
    }
  };

  const currentConfigName = currentConfig ? currentConfig.name : 'None';
  const isCustom = selectedOption === 'custom';

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium flex items-center gap-2">
        <FolderOpen className="h-4 w-4" />
        Configuration File
      </div>
      
      <div className="space-y-2">
        <Label className="text-xs">Select Profile:</Label>
        <select 
          value={selectedOption}
          onChange={(e) => setSelectedOption(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {CONFIG_OPTIONS.map((option) => (
            <option key={option.path} value={option.path}>
              {option.name}
            </option>
          ))}
        </select>
      </div>

      {isCustom && (
        <div className="space-y-2">
          <Label className="text-xs">File Path:</Label>
          <Input
            value={customPath}
            onChange={(e) => setCustomPath(e.target.value)}
            placeholder="/config/my-profile.json"
            className="text-sm"
          />
          <div className="text-xs text-muted-foreground">
            Enter path relative to public folder (e.g., /config/filename.json)
          </div>
        </div>
      )}

      <Button 
        onClick={handleLoadConfig} 
        size="sm" 
        disabled={loading || (isCustom && !customPath.trim())}
        className="gap-1 w-full"
      >
        {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <FileText className="h-3 w-3" />}
        Load Configuration
      </Button>

      <div className="text-xs text-muted-foreground border rounded p-2 bg-muted/30">
        <div className="font-medium">Current: {currentConfigName}</div>
        {currentConfig && (
          <div className="mt-1">
            <div>{currentConfig.description}</div>
            <div>Duration: {currentConfig.duration_minutes}min</div>
          </div>
        )}
      </div>
    </div>
  );
}