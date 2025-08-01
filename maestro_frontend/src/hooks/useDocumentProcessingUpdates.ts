import { useEffect } from 'react';

interface DocumentProcessingUpdate {
  type: 'document_progress';
  doc_id: string;
  document_id: string;
  progress: number;
  status: string;
  error?: string;
  user_id: string;
  timestamp: string;
}

interface UseDocumentProcessingUpdatesProps {
  onDocumentUpdate: (update: DocumentProcessingUpdate) => void;
}

export const useDocumentProcessingUpdates = ({ onDocumentUpdate }: UseDocumentProcessingUpdatesProps) => {
  // This hook is now deprecated since the UploadService already handles WebSocket connections
  // We'll keep it for compatibility but it won't create additional connections
  
  useEffect(() => {
    console.log('useDocumentProcessingUpdates: Hook initialized but using existing UploadService WebSocket');
    // No additional WebSocket connection needed - UploadService handles this
  }, [onDocumentUpdate]);
};
