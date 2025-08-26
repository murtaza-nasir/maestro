import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, CheckCircle, AlertCircle, Loader2, ChevronUp, ChevronDown, X, XCircle } from 'lucide-react';
import { useLocation } from 'react-router-dom';
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
  const { t } = useTranslation();
  const [isMinimized, setIsMinimized] = useState(false);
  const location = useLocation();
  
  useEffect(() => {
    const duplicateFiles = uploadingFiles.filter(
      f => f.status === 'error' && f.error?.includes('already been uploaded')
    );
    
    if (duplicateFiles.length > 0) {
      const timer = setTimeout(() => {
        duplicateFiles.forEach(f => onDismissFile(f.id));
      }, 5000);
      
      return () => clearTimeout(timer);
    }
  }, [uploadingFiles, onDismissFile]);

  if (uploadingFiles.length === 0) return null;

  const completedFiles = uploadingFiles.filter(f => f.status === 'completed');
  const errorFiles = uploadingFiles.filter(f => f.status === 'error');
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
        return t('uploadProgress.waiting');
      case 'uploading':
        return t('uploadProgress.uploading', { progress: file.progress });
      case 'processing':
        return t('uploadProgress.processing', { progress: file.progress });
      case 'completed':
        return t('uploadProgress.completed');
      case 'cancelled':
        return t('uploadProgress.cancelled');
      case 'error':
        return file.error || t('uploadProgress.failed');
      default:
        return t('uploadProgress.unknown');
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

  const isDocumentsPage = location.pathname === '/app/documents';
  const bottomPosition = isDocumentsPage ? 'bottom-20' : 'bottom-4';
  
  return (
    <div className={`fixed ${bottomPosition} right-4 w-full max-w-md z-50 transition-all duration-300`}>
      <div className="bg-background rounded-lg shadow-sm border border-border flex flex-col max-h-[60vh]">
        <div className="flex items-center justify-between p-3 border-b border-border cursor-pointer" onClick={handleToggleMinimize}>
          <div className="flex items-center space-x-3">
            <h2 className="text-md font-semibold text-text-primary">
              {t('uploadProgress.uploads')}
            </h2>
            <span className="text-xs text-text-secondary">
              {t('uploadProgress.completedOfTotal', { completed: completedFiles.length, total: uploadingFiles.length })}
            </span>
          </div>
          <div className="flex items-center space-x-2 text-text-secondary">
            {isMinimized ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </div>
        </div>

        {!isMinimized && (
          <>
            <div className="p-4 border-b border-border bg-background-alt">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-secondary">{t('uploadProgress.overallProgress')}</span>
                <span className="text-xs text-text-secondary">{totalProgress}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-1.5">
                <div
                  className="bg-primary h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${totalProgress}%` }}
                />
              </div>
            </div>

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
                            title={t('uploadProgress.cancelUpload')}
                          >
                            <X className="h-3 w-3 text-text-tertiary" />
                          </button>
                        )}
                        {(uploadFile.status === 'completed' || uploadFile.status === 'error' || uploadFile.status === 'cancelled') && (
                          <button
                            onClick={() => onDismissFile(uploadFile.id)}
                            className="p-1 hover:bg-background-alt rounded-full transition-colors"
                            title={t('uploadProgress.dismiss')}
                          >
                            <X className="h-3 w-3 text-text-tertiary" />
                          </button>
                        )}
                      </div>
                    </div>
                    
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
                    
                    <div className="flex items-center justify-between">
                      <p className={`text-xs flex-1 ${
                        uploadFile.status === 'error' 
                          ? uploadFile.error?.includes('already been uploaded')
                            ? 'text-amber-600 dark:text-amber-500'
                            : 'text-destructive'
                          : 'text-text-secondary'
                      }`}>{getStatusText(uploadFile)}</p>
                      {uploadFile.status === 'error' && uploadFile.error?.includes('already been uploaded') && (
                        <span className="text-xs text-muted-foreground ml-2 italic">{t('uploadProgress.autoDismiss')}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-3 border-t border-border bg-background-alt">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={onClearCompleted}
                    className="text-xs text-text-secondary hover:text-text-primary transition-colors"
                    disabled={completedFiles.length === 0}
                  >
                    {t('uploadProgress.clearCompleted')}
                  </button>
                  {errorFiles.length > 0 && (
                    <button
                      onClick={() => errorFiles.forEach(f => onDismissFile(f.id))}
                      className="text-xs text-destructive hover:text-destructive/80 transition-colors flex items-center gap-1"
                    >
                      <XCircle className="h-3 w-3" />
                      {errorFiles.length !== 1 ? t('uploadProgress.clearErrors', { count: errorFiles.length }) : t('uploadProgress.clearError', { count: errorFiles.length })}
                    </button>
                  )}
                </div>
                <button
                  onClick={onCancelAll}
                  className="text-xs text-destructive hover:text-destructive/80 transition-colors"
                  disabled={activeFiles.length === 0}
                >
                  {t('uploadProgress.cancelAll')}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
