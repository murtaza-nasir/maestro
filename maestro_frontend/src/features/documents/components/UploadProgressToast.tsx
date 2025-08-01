import React, { useState } from 'react';
import { FileText, CheckCircle, AlertCircle, Loader2, ChevronUp, ChevronDown, X } from 'lucide-react';
import type { UploadFile } from './DocumentUploadZone';

interface UploadProgressToastProps {
  uploadingFiles: UploadFile[];
  onCancelAll: () => void;
  onCancelUpload: (fileId: string) => void;
  onClearCompleted: () => void;
  onDismissFile: (fileId: string) => void;
}

export const UploadProgressToast: React.FC<UploadProgressToastProps> = ({
  uploadingFiles,
  onCancelAll,
  onCancelUpload,
  onClearCompleted,
  onDismissFile,
}) => {
  const [isMinimized, setIsMinimized] = useState(false);

  if (uploadingFiles.length === 0) return null;

  const completedFiles = uploadingFiles.filter(f => f.status === 'completed');
  const activeFiles = uploadingFiles.filter(f => 
    f.status === 'uploading' || f.status === 'processing' || f.status === 'pending'
  );

  const totalProgress = uploadingFiles.length > 0 
    ? Math.round(uploadingFiles.reduce((sum, file) => sum + file.progress, 0) / uploadingFiles.length)
    : 0;

  const getStatusIcon = (status: UploadFile['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'error':
      case 'cancelled':
        return <AlertCircle className="h-5 w-5 text-destructive" />;
      case 'uploading':
      case 'processing':
        return <Loader2 className="h-5 w-5 text-primary animate-spin" />;
      default:
        return <FileText className="h-5 w-5 text-text-secondary" />;
    }
  };

  const getStatusText = (file: UploadFile) => {
    switch (file.status) {
      case 'pending':
        return 'Waiting to upload...';
      case 'uploading':
        return `Uploading... ${file.progress}%`;
      case 'processing':
        return `Processing... ${file.progress}%`;
      case 'completed':
        return 'Upload complete';
      case 'cancelled':
        return 'Cancelled by user';
      case 'error':
        return file.error || 'Upload failed';
      default:
        return 'Unknown status';
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleToggleMinimize = () => {
    setIsMinimized(!isMinimized);
  };

  return (
    <div className="fixed bottom-4 right-4 w-full max-w-md z-50">
      <div className="bg-background rounded-lg shadow-sm border border-border flex flex-col max-h-[70vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-border cursor-pointer" onClick={handleToggleMinimize}>
          <div className="flex items-center space-x-3">
            <h2 className="text-md font-semibold text-text-primary">
              Uploads
            </h2>
            <span className="text-xs text-text-secondary">
              ({completedFiles.length}/{uploadingFiles.length} completed)
            </span>
          </div>
          <div className="flex items-center space-x-2 text-text-secondary">
            {isMinimized ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </div>

        {!isMinimized && (
          <>
            {/* Overall Progress */}
            <div className="p-4 border-b border-border bg-background-alt">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-secondary">Overall Progress</span>
                <span className="text-xs text-text-secondary">{totalProgress}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-1.5">
                <div
                  className="bg-primary h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${totalProgress}%` }}
                />
              </div>
            </div>

            {/* File List */}
            <div className="flex-1 overflow-y-auto p-3 max-h-96">
              <div className="space-y-3">
                {uploadingFiles.map((uploadFile) => (
                  <div key={uploadFile.id} className="bg-muted rounded-lg p-3 border border-border">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2 flex-1 min-w-0">
                        {getStatusIcon(uploadFile.status)}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">{uploadFile.file.name}</p>
                          <p className="text-xs text-text-secondary">{formatFileSize(uploadFile.file.size)}</p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-medium text-text-secondary">{uploadFile.progress}%</span>
                        {(uploadFile.status === 'uploading' || uploadFile.status === 'processing' || uploadFile.status === 'pending') && (
                          <button
                            onClick={() => onCancelUpload(uploadFile.id)}
                            className="p-1 hover:bg-background-alt rounded-full transition-colors"
                            title="Cancel upload"
                          >
                            <X className="h-3 w-3 text-text-tertiary" />
                          </button>
                        )}
                        {(uploadFile.status === 'completed' || uploadFile.status === 'error' || uploadFile.status === 'cancelled') && (
                          <button
                            onClick={() => onDismissFile(uploadFile.id)}
                            className="p-1 hover:bg-background-alt rounded-full transition-colors"
                            title="Dismiss"
                          >
                            <X className="h-3 w-3 text-text-tertiary" />
                          </button>
                        )}
                      </div>
                    </div>
                    
                    {/* Individual Progress Bar */}
                    <div className="w-full bg-background-alt rounded-full h-1.5 mb-1">
                      <div
                        className={`h-1.5 rounded-full transition-all duration-300 ${
                          uploadFile.status === 'completed' 
                            ? 'bg-green-500' 
                            : (uploadFile.status === 'error' || uploadFile.status === 'cancelled')
                            ? 'bg-destructive' 
                            : 'bg-primary'
                        }`}
                        style={{ width: `${uploadFile.progress}%` }}
                      />
                    </div>
                    
                    {/* Status Text */}
                    <p className="text-xs text-text-secondary">{getStatusText(uploadFile)}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-border bg-background-alt flex items-center justify-between">
              <button
                onClick={onClearCompleted}
                className="text-xs text-text-secondary hover:text-text-primary"
                disabled={completedFiles.length === 0}
              >
                Clear Completed
              </button>
              <button
                onClick={onCancelAll}
                className="text-xs text-destructive hover:text-destructive/80"
                disabled={activeFiles.length === 0}
              >
                Cancel All
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
