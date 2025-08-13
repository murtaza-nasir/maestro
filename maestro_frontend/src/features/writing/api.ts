import { apiClient } from '../../config/api';

// Types for Writing API
export interface WritingSession {
  id: string;
  name: string;
  document_group_id: string | null;
  web_search_enabled: boolean;
  created_at: string;
  updated_at: string;
  chat_id: string;
}

export interface WritingSessionCreate {
  name: string;
  document_group_id?: string | null;
  web_search_enabled?: boolean;
}

export interface WritingSessionUpdate {
  name?: string;
  document_group_id?: string | null;
  web_search_enabled?: boolean;
}

export interface Draft {
  id: string
  title: string
  writing_session_id: string
  content: string
  references: Reference[]
  created_at: string
  updated_at: string
}

export interface Reference {
  id: string;
  title: string;
  authors: string[];
  year: number;
  type: 'journal' | 'book' | 'conference' | 'web';
  url?: string;
  doi?: string;
}

export interface WritingMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface WritingChatRequest {
  message: string;
  draft_id: string;
  session_settings?: {
    model_selection?: { [key: string]: string };
    revision_settings?: { [key: string]: number };
    context_settings?: { [key: string]: any };
    operation_settings?: { [key: string]: any };
  };
  context_override?: { [key: string]: any };
  operation_mode?: string;
  document_group_id?: string | null;
  use_web_search?: boolean;
  deep_search?: boolean;
  max_search_iterations?: number;
  max_decomposed_queries?: number;
}

// Source types for writing responses
export interface WebSource {
  type: 'web';
  title: string;
  url: string;
  provider?: string;
}

export interface DocumentSource {
  type: 'document';
  title: string;
  page: string;
  doc_id: string;
  chunk_id: string;
}

export type Source = WebSource | DocumentSource;

export interface WritingChatResponse {
  message: string;
  sources: Source[];  // Add sources to the response
  operations: Array<{
    type: string;
    operation?: string;
    query?: string;
    target_element_id?: string;
    content?: string;
    references?: string[];
    revision_step?: number;
    context?: string;
    parameters?: { [key: string]: any };
  }>;
  context_used: {
    document_outline: boolean;
    full_document: boolean;
    references: boolean;
    search_results: boolean;
    conversation_history: boolean;
    document_group: boolean;
  };
  revision_steps_executed: {
    rag_search: number;
    content_generation: number;
    tool_calls: number;
    citation_search: number;
  };
  settings_applied?: { [key: string]: any };
  operation_progress?: Array<{
    operation_type: string;
    current_step: number;
    total_steps: number;
    status: string;
    description: string;
  }>;
  error?: string;
}

export interface DocumentOperation {
  operation_type: 'add_section' | 'update_section' | 'delete_section' | 'add_paragraph' | 'update_paragraph' | 'delete_paragraph';
  target_id?: string;
  data?: any;
  position?: number;
}

// Writing Sessions API
export const getWritingSessions = async (): Promise<WritingSession[]> => {
  const response = await apiClient.get('/api/writing/sessions');
  return response.data;
};


export const createWritingSession = async (sessionData: WritingSessionCreate): Promise<WritingSession> => {
  // First create a writing-specific chat for this writing session
  const chatResponse = await apiClient.post('/api/writing/chats', {
    title: sessionData.name
  });
  
  const chat = chatResponse.data;
  
  // Then create the writing session linked to the chat
  const writingSessionPayload = {
    chat_id: chat.id,
    document_group_id: sessionData.document_group_id,
    use_web_search: sessionData.web_search_enabled ?? true,
    settings: {}
  };
  
  const response = await apiClient.post('/api/writing/sessions', writingSessionPayload);
  
  // Return the session with the chat name
  return {
    ...response.data,
    name: chat.title
  };
};

export const getWritingSession = async (sessionId: string): Promise<WritingSession> => {
  const response = await apiClient.get(`/api/writing/sessions/${sessionId}`);
  return response.data;
};

export const updateWritingSession = async (sessionId: string, updates: WritingSessionUpdate): Promise<WritingSession> => {
  const response = await apiClient.put(`/api/writing/sessions/${sessionId}`, updates);
  return response.data;
};

export const deleteWritingSession = async (sessionId: string): Promise<void> => {
  await apiClient.delete(`/api/writing/sessions/${sessionId}`);
};

export const getWritingSessionByChat = async (chatId: string): Promise<WritingSession> => {
  const response = await apiClient.get(`/api/writing/sessions/by-chat/${chatId}`);
  return response.data;
};

// Draft API
export const getSessionDraft = async (sessionId: string): Promise<Draft> => {
  const response = await apiClient.get(`/api/writing/sessions/${sessionId}/draft`);
  return response.data;
};

export const updateSessionDraft = async (sessionId: string, draftData: Partial<Draft>): Promise<Draft> => {
  const response = await apiClient.put(`/api/writing/sessions/${sessionId}/draft`, draftData);
  return response.data;
};

// Enhanced Writing Chat API
export const sendWritingChatMessage = async (chatData: WritingChatRequest): Promise<WritingChatResponse> => {
  const response = await apiClient.post('/api/writing/enhanced-chat', chatData);
  return response.data;
};

// Document Operations API
export const performDocumentOperation = async (draftId: string, operation: DocumentOperation): Promise<any> => {
  const response = await apiClient.post(`/api/writing/drafts/${draftId}/operations`, operation);
  return response.data;
};

// References API
export const getDraftReferences = async (draftId: string): Promise<Reference[]> => {
  const response = await apiClient.get(`/api/writing/drafts/${draftId}/references`);
  return response.data;
};

export const addDraftReference = async (draftId: string, reference: Omit<Reference, 'id'>): Promise<Reference> => {
  const response = await apiClient.post(`/api/writing/drafts/${draftId}/references`, reference);
  return response.data;
};

export const updateDraftReference = async (draftId: string, referenceId: string, updates: Partial<Reference>): Promise<Reference> => {
  const response = await apiClient.put(`/api/writing/drafts/${draftId}/references/${referenceId}`, updates);
  return response.data;
};

export const deleteDraftReference = async (draftId: string, referenceId: string): Promise<void> => {
  await apiClient.delete(`/api/writing/drafts/${draftId}/references/${referenceId}`);
};

// Chat message management API
export const clearChatMessages = async (chatId: string): Promise<void> => {
  await apiClient.delete(`/api/chats/${chatId}/messages`);
};

export const deleteMessagePair = async (chatId: string, messageId: string): Promise<void> => {
  await apiClient.delete(`/api/chats/${chatId}/messages/${messageId}`);
};

export const deleteMessagesFromPoint = async (chatId: string, messageId: string): Promise<void> => {
  await apiClient.delete(`/api/chats/${chatId}/messages/from/${messageId}`);
};

// Writing Session Stats API
export interface WritingSessionStats {
  id: string;
  writing_session_id: string;
  total_cost: number;
  prompt_tokens: number;
  completion_tokens: number;
  native_tokens: number;
  web_searches: number;
  document_searches: number;
  created_at: string;
  updated_at: string;
}

export const getWritingSessionStats = async (sessionId: string): Promise<WritingSessionStats> => {
  const response = await apiClient.get(`/api/writing/sessions/${sessionId}/stats`);
  return response.data;
};

export const clearWritingSessionStats = async (sessionId: string): Promise<void> => {
  await apiClient.post(`/api/writing/sessions/${sessionId}/stats/clear`);
};
