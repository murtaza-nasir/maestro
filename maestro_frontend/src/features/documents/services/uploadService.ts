import { apiClient } from '../../../config/api';

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
  private websocket: WebSocket | null = null;
  private progressCallbacks: Map<string, ProgressCallback> = new Map();
  private completionCallbacks: Set<CompletionCallback> = new Set();

  constructor() {
    this.connectWebSocket();
  }

  private connectWebSocket() {
    // Get user ID and access token from auth store or API
    Promise.all([this.getUserId(), this.getAccessToken()]).then(([userId, accessToken]) => {
      if (userId && accessToken) {
        // Build WebSocket URL using nginx proxy (same origin)
        let wsBaseUrl = import.meta.env.VITE_API_WS_URL;
        
        // If no WebSocket URL is set, use relative URL (same origin through nginx proxy)
        if (!wsBaseUrl) {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          wsBaseUrl = `${protocol}//${window.location.host}`;
        }
        
        const wsUrl = `${wsBaseUrl}/ws/documents/${userId}?token=${encodeURIComponent(accessToken)}`;
        
        // console.log('Attempting to connect to WebSocket:', wsUrl);
        
        try {
          this.websocket = new WebSocket(wsUrl);
          
          this.websocket.onopen = () => {
            // console.log('Upload WebSocket connected successfully to:', wsUrl);
          };
          
          this.websocket.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              // console.log('Upload WebSocket message received:', data);
              this.handleWebSocketMessage(data);
            } catch (error) {
              console.error('Error parsing WebSocket message:', error);
            }
          };
          
          this.websocket.onclose = (event) => {
            console.log('Upload WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
            // Only attempt to reconnect if it's not a permanent failure
            if (event.code !== 1008) { // 1008 = Policy Violation (auth failure)
              setTimeout(() => this.connectWebSocket(), 3000);
            }
          };
          
          this.websocket.onerror = (error) => {
            console.error('Upload WebSocket error:', error);
            console.error('Failed to connect to:', wsUrl);
          };
        } catch (error) {
          console.error('Error creating WebSocket connection:', error);
        }
      } else {
        console.warn('Cannot connect to WebSocket: missing userId or accessToken');
        console.log('UserId:', userId, 'AccessToken present:', !!accessToken);
      }
    });
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

  private async getAccessToken(): Promise<string | null> {
    try {
      // Try to get from auth store first
      const authStore = (window as any).__AUTH_STORE__;
      if (authStore && authStore.getState) {
        const token = authStore.getState().accessToken;
        if (token) return token;
      }

      // Fallback to localStorage
      const token = localStorage.getItem('access_token');
      if (token) return token;

      // Fallback to cookies
      const cookies = document.cookie.split(';');
      for (const cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'access_token') {
          return value;
        }
      }

      return null;
    } catch (error) {
      console.error('Error getting access token:', error);
      return null;
    }
  }

  private handleWebSocketMessage(data: any) {
    console.log('Upload service received WebSocket message:', data);
    if (data.type === 'document_progress' || data.type === 'job_progress') {
      const { doc_id, document_id, progress, status, error } = data;
      const finalDocId = doc_id || document_id;

      console.log('Processing progress update for doc_id:', finalDocId);
      console.log('Current progress callbacks:', Array.from(this.progressCallbacks.keys()));

      if (finalDocId) {
        const entry = Array.from(this.progressCallbacks.entries()).find(
          ([_, value]) => value.docId === finalDocId
        );

        if (entry) {
          const [fileId, { callback }] = entry;
          console.log('Found matching callback for fileId:', fileId);
          const currentStatus = status as 'uploading' | 'processing' | 'completed' | 'error';
          
          callback({
            fileId: fileId,
            progress: progress || 0,
            status: currentStatus,
            error: error,
            documentId: finalDocId
          });

          // If the process is complete, notify completion callbacks
          if (currentStatus === 'completed') {
            console.log(`Document processing completed for ${finalDocId}. Notifying completion callbacks.`);
            this.completionCallbacks.forEach(({ callback }) => {
              try {
                callback(finalDocId);
              } catch (error) {
                console.error('Error in completion callback:', error);
              }
            });
          }

          // If the process is complete or has failed, remove the callback
          if (currentStatus === 'completed' || currentStatus === 'error') {
            console.log(`Upload for ${fileId} finished with status: ${currentStatus}. Removing callback.`);
            this.progressCallbacks.delete(fileId);
          }
        } else {
          console.log('No matching callback found for doc_id:', finalDocId);
        }
      }
    } else {
      console.log('Ignoring non-progress message type:', data.type);
    }
  }

  public async uploadFile(
    file: File,
    groupId: string,
    fileId: string,
    onProgress: (progress: UploadProgress) => void
  ): Promise<{ success: boolean; documentId?: string; error?: string }> {
    // Register progress callback
    this.progressCallbacks.set(fileId, { callback: onProgress, docId: null });

    try {
      // Initial progress
      onProgress({
        fileId,
        progress: 0,
        status: 'uploading'
      });

      const formData = new FormData();
      formData.append('file', file);

      // Upload with progress tracking
      const response = await apiClient.post(
        `/api/document-groups/${groupId}/upload/`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (progressEvent: any) => {
            if (progressEvent.total) {
              const uploadProgress = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              // Upload progress is 0-10%, processing will be 10-100%
              onProgress({
                fileId,
                progress: Math.min(uploadProgress / 10, 10),
                status: 'uploading'
              });
            }
          }
        }
      );

      // Upload completed, now processing will be handled by WebSocket
      const documentId = response.data.id;
      if (this.progressCallbacks.has(fileId)) {
        this.progressCallbacks.get(fileId)!.docId = documentId;
      }

      onProgress({
        fileId,
        progress: 10,
        status: 'processing',
        documentId
      });

      return {
        success: true,
        documentId
      };

    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Upload failed';
      
      onProgress({
        fileId,
        progress: 0,
        status: 'error',
        error: errorMessage
      });

      // Clean up the callback immediately on HTTP error
      this.progressCallbacks.delete(fileId);

      return {
        success: false,
        error: errorMessage
      };
    }
  }

  public async uploadMultipleFiles(
    files: File[],
    groupId: string,
    onProgress: (fileId: string, progress: UploadProgress) => void
  ): Promise<{ success: boolean; results: Array<{ fileId: string; success: boolean; documentId?: string; error?: string }> }> {
    const results: Array<{ fileId: string; success: boolean; documentId?: string; error?: string }> = [];
    
    // Upload files sequentially to avoid overwhelming the server
    for (const file of files) {
      const fileId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      
      const result = await this.uploadFile(
        file,
        groupId,
        fileId,
        (progress) => onProgress(fileId, progress)
      );

      results.push({
        fileId,
        success: result.success,
        documentId: result.documentId,
        error: result.error
      });
    }

    const successCount = results.filter(r => r.success).length;
    
    return {
      success: successCount > 0,
      results
    };
  }

  public onDocumentProcessingComplete(callback: (documentId: string) => void): () => void {
    const completionCallback: CompletionCallback = { callback };
    this.completionCallbacks.add(completionCallback);
    
    // Return unsubscribe function
    return () => {
      this.completionCallbacks.delete(completionCallback);
    };
  }

  public async cancelUpload(fileId: string): Promise<void> {
    try {
      // Try to cancel on the backend if we have a document ID
      const progressCallback = this.progressCallbacks.get(fileId);
      if (progressCallback && progressCallback.docId) {
        const { cancelDocumentProcessing } = await import('../api');
        await cancelDocumentProcessing(progressCallback.docId);
        console.log(`Backend processing cancelled for document: ${progressCallback.docId}`);
      }
    } catch (error) {
      console.error(`Failed to cancel upload for file ${fileId}:`, error);
    } finally {
      // Always remove the callback to stop receiving updates
      this.progressCallbacks.delete(fileId);
      console.log(`Upload cancelled for fileId: ${fileId}`);
    }
  }

  public dismissFile(fileId: string): void {
    // Remove the callback for this file (for completed/error files)
    this.progressCallbacks.delete(fileId);
    console.log(`File dismissed: ${fileId}`);
  }

  public disconnect() {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.progressCallbacks.clear();
    this.completionCallbacks.clear();
  }
}

// Singleton instance
export const uploadService = new UploadService();
