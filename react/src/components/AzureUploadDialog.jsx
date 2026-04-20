import React, { useEffect, useState } from "react";
import { useAzureUpload } from "../hooks/useAzureUpload";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Cloud, UploadCloud, CheckCircle, XCircle, Loader2, X } from "lucide-react";

/**
 * AzureUploadDialog — modal overlay for uploading the current HDF5 file to Azure.
 *
 * Props:
 *   open        – boolean controlling visibility
 *   onClose     – callback to close the dialog
 *   fileInfo    – current HDF5 file info from useHDF5Status()
 */
export function AzureUploadDialog({ open, onClose, fileInfo }) {
  const {
    status, filename, container: uploadContainer, percent,
    bytesSent, bytesTotal, error, blobUrl,
    upload, cancel, reset, fetchContainers, fetchFiles,
    isUploading, isDone, isError, isCancelled,
  } = useAzureUpload();

  const [container, setContainer] = useState("data");
  const [blobName, setBlobName] = useState("");
  const [containers, setContainers] = useState([]);
  const [loadingContainers, setLoadingContainers] = useState(false);

  // File browser state
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [loadingFiles, setLoadingFiles] = useState(false);

  // Load containers and files when dialog opens
  useEffect(() => {
    if (!open) return;
    reset();
    setLoadingContainers(true);
    setLoadingFiles(true);
    setSelectedFile(null);

    fetchContainers().then((list) => {
      setContainers(list.length > 0 ? list : ["data"]);
      setLoadingContainers(false);
    });

    fetchFiles().then((list) => {
      setFiles(list);
      setLoadingFiles(false);
      // Auto-select current file if it's in the list
      if (fileInfo?.filename && list.length > 0) {
        const match = list.find((f) => f.name === fileInfo.filename);
        if (match) {
          setSelectedFile(match);
          setBlobName(match.name);
        } else {
          setSelectedFile(list[0]);
          setBlobName(list[0].name);
        }
      } else if (list.length > 0) {
        setSelectedFile(list[0]);
        setBlobName(list[0].name);
      }
    });
  }, [open]);

  if (!open) return null;

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const handleUpload = async () => {
    try {
      await upload({
        container,
        blobName: blobName || undefined,
        filePath: selectedFile?.path || undefined,
      });
    } catch (e) {
      // error is already in state
    }
  };

  const handleClose = () => {
    if (!isUploading) {
      reset();
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Dialog */}
      <Card className="relative z-10 w-full max-w-md mx-4 shadow-xl">
        <CardContent className="p-6 space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cloud className="h-5 w-5 text-blue-500" />
              <h3 className="text-lg font-semibold">Upload til Azure</h3>
            </div>
            <button
              onClick={handleClose}
              disabled={isUploading}
              className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* File selector */}
          <div className="space-y-1.5">
            <Label className="text-xs">Vælg fil</Label>
            <div className="bg-muted/50 rounded-lg max-h-40 overflow-y-auto">
              {loadingFiles ? (
                <div className="p-3 text-xs text-muted-foreground flex items-center gap-2">
                  <Loader2 className="h-3 w-3 animate-spin" /> Søger filer...
                </div>
              ) : files.length === 0 ? (
                <div className="p-3 text-xs text-muted-foreground">
                  Ingen HDF5 filer fundet
                </div>
              ) : (
                files.map((f) => (
                  <button
                    key={f.path}
                    onClick={() => {
                      setSelectedFile(f);
                      setBlobName(f.name);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors border-b last:border-0 ${
                      selectedFile?.path === f.path
                        ? "bg-blue-50 border-l-2 border-l-blue-500"
                        : ""
                    }`}
                  >
                    <div className="font-medium truncate">{f.name}</div>
                    <div className="text-xs text-muted-foreground flex gap-3">
                      <span>{formatBytes(f.size_bytes)}</span>
                      <span>{f.modified}</span>
                      <span className="opacity-60">{f.parent}/</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Status === idle: show form */}
          {status === "idle" && (
            <>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="az-container">Container</Label>
                  <div className="flex gap-2">
                    <select
                      id="az-container"
                      value={container}
                      onChange={(e) => setContainer(e.target.value)}
                      className="flex-1 text-sm border rounded-md px-3 py-2 bg-background"
                      disabled={loadingContainers}
                    >
                      {containers.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <Input
                      placeholder="Eller skriv nyt..."
                      className="flex-1"
                      value={container}
                      onChange={(e) => setContainer(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="az-blob">Blob navn (filnavn i Azure)</Label>
                  <Input
                    id="az-blob"
                    value={blobName}
                    onChange={(e) => setBlobName(e.target.value)}
                    placeholder={fileInfo?.filename || "scope_data.h5"}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={handleClose}>
                  Annuller
                </Button>
                <Button
                  onClick={handleUpload}
                  disabled={!selectedFile || !container}
                  className="gap-2"
                >
                  <UploadCloud className="h-4 w-4" />
                  Upload
                </Button>
              </div>
            </>
          )}

          {/* Status === uploading: show progress */}
          {status === "uploading" && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                    Uploader...
                  </span>
                  <span className="font-mono text-muted-foreground">
                    {percent}%
                  </span>
                </div>

                {/* Progress bar */}
                <div className="w-full h-3 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${Math.max(2, percent)}%` }}
                  />
                </div>

                <div className="text-xs text-muted-foreground text-right">
                  {formatBytes(bytesSent)} / {formatBytes(bytesTotal)}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Luk ikke dette vindue under upload
                </p>
                <Button variant="destructive" size="sm" onClick={cancel}>
                  Annuller
                </Button>
              </div>
            </div>
          )}

          {/* Status === cancelled */}
          {status === "cancelled" && (
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-2 py-2">
                <XCircle className="h-10 w-10 text-muted-foreground" />
                <p className="font-medium">Upload annulleret</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(bytesSent)} af {formatBytes(bytesTotal)} blev uploadet
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={handleClose}>Luk</Button>
                <Button onClick={() => { reset(); }}>Prøv igen</Button>
              </div>
            </div>
          )}

          {/* Status === done: success */}
          {status === "done" && (
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-2 py-2">
                <CheckCircle className="h-10 w-10 text-green-500" />
                <p className="font-medium text-green-700">Upload færdig!</p>
                <div className="text-xs text-muted-foreground text-center space-y-1">
                  <p>{filename} → {uploadContainer}</p>
                  <p>{formatBytes(bytesTotal)}</p>
                </div>
                {blobUrl && (
                  <Badge variant="outline" className="text-xs mt-1 max-w-full truncate">
                    {blobUrl}
                  </Badge>
                )}
              </div>

              <div className="flex justify-end">
                <Button onClick={handleClose}>Luk</Button>
              </div>
            </div>
          )}

          {/* Status === error */}
          {status === "error" && (
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-2 py-2">
                <XCircle className="h-10 w-10 text-destructive" />
                <p className="font-medium text-destructive">Upload fejlede</p>
                <p className="text-xs text-muted-foreground text-center break-all">
                  {error}
                </p>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={handleClose}>Luk</Button>
                <Button onClick={() => { reset(); }}>Prøv igen</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
