import { useState, useCallback, useEffect } from 'react';
import { uploadService, type UploadProgress } from '../services/uploadService';
import type { UploadFile } from '../components/DocumentUploadZone';

export interface UseDocumentUploadOptions {
  onUploadComplete?: (documentId: string, filename: string) => void;
  onUploadError?: (filename: string, error: string) => void;
  onAllUploadsComplete?: () => void;
}

export const useDocumentUpload = (options: UseDocumentUploadOptions = {}) => {
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

    // Check if this file completed successfully
    if (progress.status === 'completed' && progress.documentId) {
      const file = uploadingFiles.find(f => f.id === fileId);
      if (file) {
        options.onUploadComplete?.(progress.documentId, file.file.name);
      }
    }

    // Check if this file failed
    if (progress.status === 'error' && progress.error) {
      const file = uploadingFiles.find(f => f.id === fileId);
      if (file) {
        options.onUploadError?.(file.file.name, progress.error);
      }
    }
  }, [uploadingFiles, options]);

  const startUploads = useCallback(async (files: File[], groupId: string) => {
    if (!groupId) {
      console.error('No group ID provided for upload');
      return;
    }

    // Create upload file objects
    const newUploadFiles: UploadFile[] = files.map(file => ({
      id: generateFileId(),
      file,
      status: 'pending',
      progress: 0
    }));

    setUploadingFiles(prev => [...prev, ...newUploadFiles]);

    // Start uploads sequentially
    for (const uploadFile of newUploadFiles) {
      try {
        await uploadService.uploadFile(
          uploadFile.file,
          groupId,
          uploadFile.id,
          (progress) => updateFileProgress(uploadFile.id, progress)
        );
      } catch (error: any) {
        console.error('Upload error:', error);
        
        // Handle duplicate file error (409) with user-friendly message
        let errorMessage = 'Upload failed';
        if (error.response?.status === 409) {
          errorMessage = `This file has already been uploaded: ${uploadFile.file.name}`;
        } else if (error.response?.data?.detail) {
          errorMessage = error.response.data.detail;
        } else if (error.message) {
          errorMessage = error.message;
        }
        
        updateFileProgress(uploadFile.id, {
          fileId: uploadFile.id,
          progress: 0,
          status: 'error',
          error: errorMessage
        });
      }
    }

    // Check if all uploads are complete
    setTimeout(() => {
      const allComplete = uploadingFiles.every(f => 
        f.status === 'completed' || f.status === 'error'
      );
      if (allComplete) {
        options.onAllUploadsComplete?.();
      }
    }, 1000);

  }, [updateFileProgress, uploadingFiles, options]);

  const retryUpload = useCallback(async (fileId: string, groupId: string) => {
    const file = uploadingFiles.find(f => f.id === fileId);
    if (!file || !groupId) return;

    // Reset file status
    setUploadingFiles(prev =>
      prev.map(f =>
        f.id === fileId
          ? { ...f, status: 'pending', progress: 0, error: undefined }
          : f
      )
    );

    try {
      await uploadService.uploadFile(
        file.file,
        groupId,
        fileId,
        (progress) => updateFileProgress(fileId, progress)
      );
    } catch (error: any) {
      console.error('Retry upload error:', error);
      
      // Handle duplicate file error (409) with user-friendly message
      let errorMessage = 'Upload failed';
      if (error.response?.status === 409) {
        errorMessage = `This file has already been uploaded: ${file.file.name}`;
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      updateFileProgress(fileId, {
        fileId,
        progress: 0,
        status: 'error',
        error: errorMessage
      });
    }
  }, [uploadingFiles, updateFileProgress]);

  const removeFile = useCallback((fileId: string) => {
    setUploadingFiles(prev => prev.filter(f => f.id !== fileId));
  }, []);

  const cancelAllUploads = useCallback(() => {
    // Cancel pending and uploading files
    setUploadingFiles(prev =>
      prev.map(file =>
        file.status === 'pending' || file.status === 'uploading'
          ? { ...file, status: 'error', error: 'Cancelled by user' }
          : file
      )
    );
  }, []);

  const clearCompleted = useCallback(() => {
    setUploadingFiles(prev => prev.filter(f => f.status !== 'completed'));
  }, []);

  const clearCompletedUploads = clearCompleted;

  // Clean up on unmount
  useEffect(() => {
    return () => {
      uploadService.disconnect();
    };
  }, []);

  return {
    uploadingFiles,
    startUploads,
    retryUpload,
    removeFile,
    cancelAllUploads,
    clearCompleted,
    clearCompletedUploads
  };
};
