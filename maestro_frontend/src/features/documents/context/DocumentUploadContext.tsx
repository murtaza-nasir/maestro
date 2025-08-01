import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { uploadService, type UploadProgress } from '../services/uploadService';
import type { UploadFile } from '../components/DocumentUploadZone';

interface DocumentUploadContextType {
  uploadingFiles: UploadFile[];
  startUploads: (files: File[], groupId: string) => void;
  retryUpload: (fileId: string, groupId: string) => void;
  cancelUpload: (fileId: string) => void;
  cancelAllUploads: () => void;
  clearCompletedUploads: () => void;
  dismissFile: (fileId: string) => void;
}

const DocumentUploadContext = createContext<DocumentUploadContextType | undefined>(undefined);

export const DocumentUploadProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [uploadingFiles, setUploadingFiles] = useState<UploadFile[]>([]);

  const generateFileId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  const updateFileProgress = useCallback((fileId: string, progress: UploadProgress) => {
    setUploadingFiles(prev =>
      prev.map(file =>
        file.id === fileId
          ? {
              ...file,
              status: progress.status,
              progress: progress.progress,
              error: progress.error,
              documentId: progress.documentId
            }
          : file
      )
    );
  }, []);

  const startUploads = useCallback(async (files: File[], groupId: string) => {
    const newUploadFiles: UploadFile[] = files.map(file => ({
      id: generateFileId(),
      file,
      status: 'pending',
      progress: 0
    }));

    setUploadingFiles(prev => [...prev, ...newUploadFiles]);

    for (const uploadFile of newUploadFiles) {
      await uploadService.uploadFile(
        uploadFile.file,
        groupId,
        uploadFile.id,
        (progress) => updateFileProgress(uploadFile.id, progress)
      );
    }
  }, [updateFileProgress]);

  const retryUpload = useCallback(async (fileId: string, groupId: string) => {
    const file = uploadingFiles.find(f => f.id === fileId);
    if (!file) return;

    setUploadingFiles(prev =>
      prev.map(f =>
        f.id === fileId
          ? { ...f, status: 'pending', progress: 0, error: undefined }
          : f
      )
    );

    await uploadService.uploadFile(
      file.file,
      groupId,
      fileId,
      (progress) => updateFileProgress(fileId, progress)
    );
  }, [uploadingFiles, updateFileProgress]);

  const cancelUpload = useCallback((fileId: string) => {
    uploadService.cancelUpload(fileId);
    setUploadingFiles(prev =>
      prev.map(file =>
        file.id === fileId && (file.status === 'pending' || file.status === 'uploading' || file.status === 'processing')
          ? { ...file, status: 'cancelled', error: 'Cancelled by user' }
          : file
      )
    );
  }, []);

  const cancelAllUploads = useCallback(() => {
    setUploadingFiles(prev =>
      prev.map(file => {
        if (file.status === 'pending' || file.status === 'uploading' || file.status === 'processing') {
          uploadService.cancelUpload(file.id);
          return { ...file, status: 'cancelled', error: 'Cancelled by user' };
        }
        return file;
      })
    );
  }, []);

  const clearCompletedUploads = useCallback(() => {
    setUploadingFiles(prev => prev.filter(f => f.status !== 'completed' && f.status !== 'error' && f.status !== 'cancelled'));
  }, []);

  const dismissFile = useCallback((fileId: string) => {
    uploadService.dismissFile(fileId);
    setUploadingFiles(prev => prev.filter(f => f.id !== fileId));
  }, []);

  useEffect(() => {
    return () => {
      uploadService.disconnect();
    };
  }, []);

  return (
    <DocumentUploadContext.Provider
      value={{
        uploadingFiles,
        startUploads,
        retryUpload,
        cancelUpload,
        cancelAllUploads,
        clearCompletedUploads,
        dismissFile,
      }}
    >
      {children}
    </DocumentUploadContext.Provider>
  );
};

export const useDocumentUploadManager = () => {
  const context = useContext(DocumentUploadContext);
  if (context === undefined) {
    throw new Error('useDocumentUploadManager must be used within a DocumentUploadProvider');
  }
  return context;
};
