import { apiClient, API_CONFIG } from '../../config/api'

export interface Message {
  id: string
  content: string
  role: 'user' | 'assistant'
  created_at: string
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
  missions: Mission[]
  created_at: string
  updated_at: string
  user_id: number
  document_group_id?: string
}

export interface ChatSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  user_id: number
  message_count: number
  active_mission_count: number
}

export interface Mission {
  id: string
  chat_id: string
  user_request: string
  status: string
  mission_context?: any
  error_info?: string
  created_at: string
  updated_at: string
}

export interface CreateChatRequest {
  title: string
}

export interface UpdateChatRequest {
  title: string
}

export interface CreateMessageRequest {
  content: string
  role: 'user' | 'assistant'
}

// Chat API functions
export const createChat = async (data: CreateChatRequest): Promise<Chat> => {
  const response = await apiClient.post(API_CONFIG.ENDPOINTS.CHATS.CREATE, data)
  return response.data
}

export const getUserChats = async (skip = 0, limit = 100): Promise<ChatSummary[]> => {
  const response = await apiClient.get(API_CONFIG.ENDPOINTS.CHATS.LIST, {
    params: { skip, limit }
  })
  return response.data
}

export const getChat = async (chatId: string): Promise<Chat> => {
  const response = await apiClient.get(API_CONFIG.ENDPOINTS.CHATS.GET.replace(':id', chatId))
  return response.data
}

export const updateChat = async (chatId: string, data: UpdateChatRequest): Promise<Chat> => {
  const response = await apiClient.put(API_CONFIG.ENDPOINTS.CHATS.UPDATE.replace(':id', chatId), data)
  return response.data
}

export const deleteChat = async (chatId: string): Promise<void> => {
  await apiClient.delete(API_CONFIG.ENDPOINTS.CHATS.DELETE.replace(':id', chatId))
}

export const addMessageToChat = async (chatId: string, data: CreateMessageRequest): Promise<Message> => {
  const response = await apiClient.post(`/api/chats/${chatId}/messages`, data)
  return response.data
}

export const getChatMessages = async (chatId: string, skip = 0, limit = 100): Promise<Message[]> => {
  const response = await apiClient.get(`/api/chats/${chatId}/messages`, {
    params: { skip, limit }
  })
  return response.data
}

export const getChatMissions = async (chatId: string): Promise<Mission[]> => {
  const response = await apiClient.get(`/api/chats/${chatId}/missions`)
  return response.data
}

export const getActiveChatMissions = async (chatId: string): Promise<Mission[]> => {
  const response = await apiClient.get(`/api/chats/${chatId}/active-missions`)
  return response.data
}
