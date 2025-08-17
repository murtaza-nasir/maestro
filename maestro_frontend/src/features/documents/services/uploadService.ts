/**
 * Document Upload Service - now uses UnifiedWebSocketService
 * Handles document upload progress tracking via WebSocket
 */
import { apiClient } from '../../../config/api';
import { unifiedWebSocketService } from '../../../services/unifiedWebSocketService';

export interface UploadProgress {
  fileId: string;
  progress: number;
  status: 'uploading' | 'processing' | 'completed' | 'error';
  error?: string;
  documentId?: string;
}

interface ProgressCallback {
  callback: (progress: UploadProgress) => void;
  docId: string | null;
}

interface CompletionCallback {
  callback: (documentId: string) => void;
}

export class UploadService {
  private progressCallbacks: Map<string, ProgressCallback> = new Map();
  private completionCallbacks: Set<CompletionCallback> = new Set();
  private connectionKey: string | null = null;
  private userId: number | null = null;
  private connectionPromise: Promise<void> | null = null;

  constructor() {
    // Connect on first use
    this.ensureConnection();
  }

  private async ensureConnection(): Promise<void> {
    // Return existing connection promise if connecting
    if (this.connectionPromise) {
      return this.connectionPromise;
    }

    // Already connected
    if (this.connectionKey && unifiedWebSocketService.isConnected(this.connectionKey)) {
      return Promise.resolve();
    }

    // Create new connection promise
    this.connectionPromise = this.connectWebSocket();
    return this.connectionPromise;
  }

  private async connectWebSocket(): Promise<void> {
    try {
      // Get user ID if not already cached
      if (!this.userId) {
        this.userId = await this.getUserId();
      }

      if (!this.userId) {
        console.warn('Cannot connect to upload WebSocket: missing userId');
        throw new Error('User ID not available');
      }

      // Use unified service for connection
      this.connectionKey = await unifiedWebSocketService.getConnection({
        endpoint: `/ws/documents/${this.userId}`,
        connectionType: 'document',
        onMessage: (message) => this.handleWebSocketMessage(message),
        onConnect: () => {
          // console.log('Document upload WebSocket connected');
        },
        onDisconnect: () => {
          // console.log('Document upload WebSocket disconnected');
          // Clear connection key to trigger reconnection on next use
          this.connectionKey = null;
          this.connectionPromise = null;
        },
        onError: (error) => {
          console.error('Document upload WebSocket error:', error);
          this.connectionKey = null;
          this.connectionPromise = null;
        }
      });
    } catch (error) {
      console.error('Failed to connect document upload WebSocket:', error);
      this.connectionPromise = null;
      throw error;
    }
  }

  private async getUserId(): Promise<number | null> {
    try {
      // This would typically come from your auth store
      // For now, we'll make a simple API call to get current user
      const response = await apiClient.get('/api/auth/me');
      return response.data.id;
    } catch (error) {
      console.error('Error getting user ID:', error);
      return null;
    }
  }

  private handleWebSocketMessage(data: any) {
    // console.log('Upload service received WebSocket message:', data);
    
    if (data.type === 'connection_established') {
      // Connection confirmed
      return;
    }
    
    if (data.type === 'document_progress') {
      const docId = data.doc_id || data.document_id;
      
      // Find callbacks by document ID
      const relevantCallbacks = Array.from(this.progressCallbacks.entries())
        .filter(([_, callbackInfo]) => callbackInfo.docId === docId);
      
      if (relevantCallbacks.length > 0) {
        relevantCallbacks.forEach(([fileId, callbackInfo]) => {
          const progress: UploadProgress = {
            fileId: fileId, // Use the original fileId for UI updates
            progress: data.progress || 0,
            status: data.status || 'processing',
            error: data.error,
            documentId: docId
          };
          
          // Map status values
          if (data.status === 'completed') {
            progress.status = 'completed';
            progress.progress = 100;
          } else if (data.status === 'error' || data.status === 'failed' || data.error) {
            progress.status = 'error';
          } else if (data.status === 'processing') {
            progress.status = 'processing';
          }
          
          // Call the specific callback
          try {
            callbackInfo.callback(progress);
          } catch (error) {
            console.error('Error in progress callback:', error);
          }
        });
        
        // If completed, notify completion callbacks
        if (data.status === 'completed') {
          this.notifyCompletionCallbacks(docId);
        }
      } else {
        // console.log(`No callbacks found for document ${docId}`);
      }
    } else if (data.type === 'job_progress') {
      // Handle job progress updates
      const docId = data.doc_id || data.job_id;
      
      // Find callbacks by document ID
      const relevantCallbacks = Array.from(this.progressCallbacks.entries())
        .filter(([_, callbackInfo]) => callbackInfo.docId === docId);
      
      if (relevantCallbacks.length > 0) {
        relevantCallbacks.forEach(([fileId, callbackInfo]) => {
          const progress: UploadProgress = {
            fileId: fileId,
            progress: data.progress || 0,
            status: data.status === 'completed' ? 'completed' : 'processing',
            error: data.error,
            documentId: docId
          };
          
          if (data.status === 'completed') {
            progress.progress = 100;
          }
          
          // Call the specific callback
          try {
            callbackInfo.callback(progress);
          } catch (error) {
            console.error('Error in progress callback:', error);
          }
        });
        
        if (data.status === 'completed') {
          this.notifyCompletionCallbacks(docId);
        }
      }
    } else {
      // console.log('Ignoring non-progress message type:', data.type);
    }
  }

  private notifyProgressCallbacks(progress: UploadProgress) {
    this.progressCallbacks.forEach((callbackInfo) => {
      // Only notify if this callback is interested in this document
      if (callbackInfo.docId === null || callbackInfo.docId === progress.fileId) {
        try {
          callbackInfo.callback(progress);
        } catch (error) {
          console.error('Error in progress callback:', error);
        }
      }
    });
  }

  private notifyCompletionCallbacks(documentId: string) {
    this.completionCallbacks.forEach((callbackInfo) => {
      try {
        callbackInfo.callback(documentId);
      } catch (error) {
        console.error('Error in completion callback:', error);
      }
    });
  }

  public async uploadFiles(files: File[], documentGroupId?: string): Promise<void> {
    // Ensure WebSocket is connected before uploading
    await this.ensureConnection();

    // Upload files one by one since the backend expects single file uploads
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file); // Changed from 'files' to 'file' to match backend expectation

      try {
        if (documentGroupId) {
          // If we have a group ID, use the group upload endpoint
          await apiClient.post(`/api/document-groups/${documentGroupId}/upload/`, formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });
        } else {
          // Otherwise use the regular upload endpoint
          await apiClient.post('/api/documents/upload', formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });
        }
      } catch (error: any) {
        // Handle duplicate file error (409) gracefully
        if (error.response?.status === 409) {
          console.log(`File ${file.name} already exists in the database, skipping.`);
          // Continue with the next file instead of throwing
          continue;
        }
        // Re-throw other errors
        throw error;
      }
    }
  }

  public onProgress(callback: (progress: UploadProgress) => void, docId: string | null = null): () => void {
    const id = Date.now().toString() + Math.random().toString(36);
    const callbackInfo: ProgressCallback = { callback, docId };
    this.progressCallbacks.set(id, callbackInfo);
    
    // Return unsubscribe function
    return () => {
      this.progressCallbacks.delete(id);
    };
  }

  public onCompletion(callback: (documentId: string) => void): () => void {
    const callbackObj: CompletionCallback = { callback };
    this.completionCallbacks.add(callbackObj);
    
    // Return unsubscribe function
    return () => {
      this.completionCallbacks.delete(callbackObj);
    };
  }

  public async uploadFile(
    file: File,
    documentGroupId: string,
    fileId: string,
    onProgress: (progress: UploadProgress) => void
  ): Promise<void> {
    // Ensure WebSocket is connected before uploading
    await this.ensureConnection();
    
    // Store the progress callback for this specific file
    this.progressCallbacks.set(fileId, { callback: onProgress, docId: fileId });
    
    // Upload the file and get the document ID from the response
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await apiClient.post(
        documentGroupId 
          ? `/api/document-groups/${documentGroupId}/upload/`
          : '/api/documents/upload',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      );
      
      // The backend returns the actual document ID
      const docId = response.data.id;
      
      if (docId) {
        // Update our callback mapping to use the real document ID
        const callbackInfo = this.progressCallbacks.get(fileId);
        if (callbackInfo) {
          // Remove old mapping and add new one with actual doc ID
          this.progressCallbacks.delete(fileId);
          this.progressCallbacks.set(docId, { ...callbackInfo, docId });
          
          // Also keep the fileId mapping for UI updates
          this.progressCallbacks.set(fileId, { ...callbackInfo, docId });
        }
        
        // Send initial progress update
        onProgress({
          fileId: fileId,
          progress: 10,
          status: 'processing',
          documentId: docId
        });
      }
    } catch (error: any) {
      console.error('Upload error:', error);
      
      // Handle duplicate file error (409) with user-friendly message
      let errorMessage = 'Upload failed';
      
      if (error.response?.status === 409) {
        const duplicateFilename = error.response.data?.filename || file.name;
        errorMessage = `This file has already been uploaded: ${duplicateFilename}`;
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      // Send error update with user-friendly message
      onProgress({
        fileId: fileId,
        progress: 0,
        status: 'error',
        error: errorMessage
      });
      
      // Don't throw for duplicate files, just notify
      if (error.response?.status !== 409) {
        throw error;
      }
    }
  }

  public cancelUpload(fileId: string) {
    // For now, just remove the progress callback
    // In a real implementation, you'd cancel the actual upload request
    this.progressCallbacks.delete(fileId);
    console.log(`Upload cancelled for file: ${fileId}`);
  }

  public dismissFile(fileId: string) {
    // Remove the progress callback for dismissed file
    this.progressCallbacks.delete(fileId);
    // console.log(`File dismissed: ${fileId}`);
  }

  public onDocumentProcessingComplete(callback: (documentId: string) => void): () => void {
    // This is the same as onCompletion but with a different signature
    const callbackObj: CompletionCallback = { callback };
    this.completionCallbacks.add(callbackObj);
    
    // Return unsubscribe function
    return () => {
      this.completionCallbacks.delete(callbackObj);
    };
  }

  public disconnect() {
    // Don't actually disconnect - let unified service manage
    // Just clear our local state
    this.progressCallbacks.clear();
    this.completionCallbacks.clear();
    this.connectionKey = null;
    this.userId = null;
    this.connectionPromise = null;
  }
}

// Export singleton instance
export const uploadService = new UploadService();