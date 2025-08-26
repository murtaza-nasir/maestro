import React from 'react';
import { useTranslation } from 'react-i18next';
import { X, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { UploadFile } from './DocumentUploadZone';

interface UploadProgressModalProps {
  isOpen: boolean;
  onClose: () => void;
  uploadingFiles: UploadFile[];
  onRetryFile: (fileId: string) => void;
  onCancelFile: (fileId: string) => void;
  onCancelAll: () => void;
}

export const UploadProgressModal: React.FC<UploadProgressModalProps> = ({
  isOpen,
  onClose,
  uploadingFiles,
  onRetryFile,
  onCancelFile,
  onCancelAll
}) => {
  const { t } = useTranslation();
  if (!isOpen) return null;

  const completedFiles = uploadingFiles.filter(f => f.status === 'completed');
  const failedFiles = uploadingFiles.filter(f => f.status === 'error');
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
        return t('uploadProgressModal.waiting');
      case 'uploading':
        return t('uploadProgressModal.uploading', { progress: file.progress });
      case 'processing':
        return t('uploadProgressModal.processing', { progress: file.progress });
      case 'completed':
        return t('uploadProgressModal.completed');
      case 'error':
        return file.error || t('uploadProgressModal.failed');
      default:
        return t('uploadProgressModal.unknown');
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const canClose = activeFiles.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="absolute inset-0 bg-black bg-opacity-50"
        onClick={canClose ? onClose : undefined}
      />
      
      <div className="relative bg-background rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col border border-border">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div className="flex items-center space-x-3">
            <h2 className="text-xl font-semibold text-text-primary">
              {t('uploadProgressModal.title')}
            </h2>
            <span className="text-sm text-text-secondary">
              {t('uploadProgressModal.completedOfTotal', { completed: completedFiles.length, total: uploadingFiles.length })}
            </span>
          </div>
          
          <div className="flex items-center space-x-2">
            {activeFiles.length > 0 && (
              <button
                onClick={onCancelAll}
                className="text-sm text-destructive hover:text-destructive/80 px-3 py-1 rounded"
              >
                {t('uploadProgressModal.cancelAll')}
              </button>
            )}
            <button
              onClick={onClose}
              disabled={!canClose}
              className={cn(
                "text-text-tertiary hover:text-text-secondary",
                !canClose && "opacity-50 cursor-not-allowed"
              )}
            >
              <X className="h-6 w-6" />
            </button>
          </div>
        </div>

        <div className="p-6 border-b border-border bg-background-alt">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-text-secondary">
              {t('uploadProgressModal.overallProgress')}
            </span>
            <span className="text-sm text-text-secondary">
              {totalProgress}%
            </span>
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all duration-300"
              style={{ width: `${totalProgress}%` }}
            />
          </div>
          
          <div className="flex items-center justify-between mt-3 text-sm">
            <div className="flex items-center space-x-4">
              {completedFiles.length > 0 && (
                <span className="text-green-500">
                  ✓ {t('uploadProgressModal.completedCount', { count: completedFiles.length })}
                </span>
              )}
              {failedFiles.length > 0 && (
                <span className="text-destructive">
                  ✗ {t('uploadProgressModal.failedCount', { count: failedFiles.length })}
                </span>
              )}
              {activeFiles.length > 0 && (
                <span className="text-primary">
                  ⟳ {t('uploadProgressModal.inProgressCount', { count: activeFiles.length })}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-4">
            {uploadingFiles.map((uploadFile) => (
              <div
                key={uploadFile.id}
                className={cn(
                  "flex items-center space-x-4 p-4 rounded-lg border",
                  uploadFile.status === 'completed' && "bg-green-500/10 border-green-500/20",
                  uploadFile.status === 'error' && "bg-destructive/10 border-destructive/20",
                  (uploadFile.status === 'uploading' || uploadFile.status === 'processing') && "bg-primary/10 border-primary/20",
                  uploadFile.status === 'pending' && "bg-muted border-border"
                )}
              >
                {getStatusIcon(uploadFile.status)}
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {uploadFile.file.name}
                    </p>
                    <span className="text-xs text-text-secondary ml-2">
                      {formatFileSize(uploadFile.file.size)}
                    </span>
                  </div>
                  
                  <p className="text-xs text-text-secondary mb-2">
                    {getStatusText(uploadFile)}
                  </p>
                  
                  {(uploadFile.status === 'uploading' || uploadFile.status === 'processing') && (
                    <div className="w-full bg-muted rounded-full h-1.5">
                      <div
                        className={cn(
                          "h-1.5 rounded-full transition-all duration-300",
                          uploadFile.status === 'uploading' ? "bg-primary" : "bg-purple-500"
                        )}
                        style={{ width: `${uploadFile.progress}%` }}
                      />
                    </div>
                  )}
                </div>
                
                <div className="flex items-center space-x-2">
                  {uploadFile.status === 'error' && (
                    <button
                      onClick={() => onRetryFile(uploadFile.id)}
                      className="text-xs text-primary hover:text-primary/80 px-2 py-1 rounded border border-primary/20 hover:bg-primary/10"
                    >
                      {t('uploadProgressModal.retry')}
                    </button>
                  )}
                  
                  {(uploadFile.status === 'pending' || uploadFile.status === 'uploading') && (
                    <button
                      onClick={() => onCancelFile(uploadFile.id)}
                      className="text-xs text-destructive hover:text-destructive/80 px-2 py-1 rounded border border-destructive/20 hover:bg-destructive/10"
                    >
                      {t('uploadProgressModal.cancel')}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {canClose && (
          <div className="p-6 border-t border-border bg-background-alt">
            <div className="flex items-center justify-between">
              <div className="text-sm text-text-secondary">
                {completedFiles.length > 0 && failedFiles.length === 0 && (
                  <span className="text-green-500 font-medium">
                    {t('uploadProgressModal.allCompleted')}
                  </span>
                )}
                {failedFiles.length > 0 && (
                  <span className="text-destructive font-medium">
                    {t('uploadProgressModal.someFailed', { count: failedFiles.length })}
                  </span>
                )}
              </div>
              
              <button
                onClick={onClose}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/80 transition-colors"
              >
                {t('uploadProgressModal.close')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
