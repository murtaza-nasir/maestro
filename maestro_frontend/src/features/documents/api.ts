import { apiClient } from '../../config/api';
import type { DocumentGroup, DocumentGroupWithCount, Document } from './types';

export const getDocumentGroups = async (): Promise<DocumentGroupWithCount[]> => {
  const response = await apiClient.get('/api/document-groups/');
  return response.data;
};

export const createDocumentGroup = async (name: string): Promise<DocumentGroup> => {
  const response = await apiClient.post('/api/document-groups/', { name });
  return response.data;
};

export const renameDocumentGroup = async (id: string, name: string): Promise<DocumentGroup> => {
  const response = await apiClient.put(`/api/document-groups/${id}`, { name });
  return response.data;
};

export const deleteDocumentGroup = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/document-groups/${id}`);
};

export const getDocuments = async (groupId: string): Promise<Document[]> => {
  const response = await apiClient.get(`/api/document-groups/${groupId}/documents/`);
  return response.data;
};

export const uploadDocument = async (groupId: string, file: File): Promise<Document> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post(`/api/document-groups/${groupId}/upload/`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// Pagination and filtering types
export interface PaginationParams {
  page?: number;
  limit?: number;
  search?: string;
  author?: string;
  year?: number;
  journal?: string;
  status?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface PaginationInfo {
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedDocumentResponse {
  documents: Document[];
  pagination: PaginationInfo;
  filters_applied: Record<string, any>;
}

// New API calls for the existing document store
export const getAllDocuments = async (params?: PaginationParams): Promise<PaginatedDocumentResponse> => {
  const response = await apiClient.get('/api/all-documents/', { params });
  return response.data;
};

export const getGroupDocuments = async (groupId: string, params?: PaginationParams): Promise<PaginatedDocumentResponse> => {
  const response = await apiClient.get(`/api/document-groups/${groupId}/documents/`, { params });
  return response.data;
};

export const searchDocuments = async (query: string, nResults: number = 10): Promise<any> => {
  const response = await apiClient.get('/api/search/', {
    params: { query, n_results: nResults }
  });
  return response.data;
};

export const addExistingDocumentToGroup = async (groupId: string, docId: string): Promise<void> => {
  await apiClient.post(`/api/document-groups/${groupId}/add-document/${docId}`);
};

export const deleteDocument = async (documentId: string): Promise<void> => {
  await apiClient.delete(`/api/documents/${documentId}`);
};

// Bulk operations
export const bulkDeleteDocuments = async (documentIds: string[]): Promise<void> => {
  await apiClient.post('/api/documents/bulk-delete', documentIds);
};

export const bulkAddDocumentsToGroup = async (groupId: string, documentIds: string[]): Promise<any> => {
  const response = await apiClient.post(`/api/document-groups/${groupId}/bulk-add-documents`, documentIds);
  return response.data;
};

export const bulkRemoveDocumentsFromGroup = async (groupId: string, documentIds: string[]): Promise<any> => {
  const response = await apiClient.post(`/api/document-groups/${groupId}/bulk-remove-documents`, documentIds);
  return response.data;
};

export const cancelDocumentProcessing = async (docId: string): Promise<any> => {
  const response = await apiClient.post(`/api/documents/${docId}/cancel`);
  return response.data;
};
