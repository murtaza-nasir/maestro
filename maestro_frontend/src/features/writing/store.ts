import { create } from 'zustand'
import * as writingApi from './api'
import type { WritingSession, WritingSessionCreate, Draft, WritingMessage, Source } from './api'
// import { missionWebSocket } from '../../services/websocket'
import { ensureDate } from '../../utils/timezone'

export type { Draft };

// Chat interface for writing chats
interface Chat {
  id: string
  title: string
  created_at: string
  updated_at: string
  chat_type: string
}

// Extended message type to include sources and proper timestamp handling
interface WritingMessageWithSources extends Omit<WritingMessage, 'created_at'> {
  sources?: Source[]
  timestamp: Date  // Use Date object like research chat for proper timezone handling
}

interface WritingState {
  // Current session and draft
  currentSession: WritingSession | null
  currentDraft: Draft | null
  
  // Chat messages - now organized by chat ID
  messagesByChat: Record<string, WritingMessageWithSources[]> // chatId -> messages
  loadingStates: Record<string, boolean> // sessionId -> isLoading
  error: string | null
  
  // Available sessions
  sessions: WritingSession[]
  
  // Chat management (for writing chats)
  chats: Chat[]
  activeChat: Chat | null
  isLoading: boolean
  
  // WebSocket status
  isWebSocketConnected: boolean
  agentStatus: Record<string, string> // sessionId -> status
  
  // Actions
  setCurrentSession: (session: WritingSession | null) => void
  setCurrentDraft: (draft: Draft | null) => void
  addMessage: (message: WritingMessageWithSources) => void
  clearMessages: () => void
  setSessionLoading: (sessionId: string, loading: boolean) => void
  getSessionLoading: (sessionId: string) => boolean
  clearError: () => void
  setWebSocketConnected: (connected: boolean) => void
  setAgentStatus: (sessionId: string, status: string) => void
  getCurrentAgentStatus: () => string
  
  // Computed getters
  getCurrentMessages: () => WritingMessageWithSources[]
  
  // Session management
  loadSessions: () => Promise<void>
  createSession: (sessionData: WritingSessionCreate) => Promise<WritingSession>
  selectSession: (sessionId: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  
  // Chat management (for writing chats)
  loadChats: () => Promise<void>
  createChat: (title?: string) => Promise<Chat>
  setActiveChat: (chatId: string) => Promise<void>
  deleteChat: (chatId: string) => Promise<void>
  
  // Draft management
  loadDraft: (sessionId: string) => Promise<void>
  saveDraftChanges: (content: string, title?: string) => Promise<void>
  
  // Enhanced chat
  sendMessage: (message: string, options?: { documentGroupId?: string | null; useWebSearch?: boolean; deepSearch?: boolean; maxIterations?: number; maxQueries?: number }) => Promise<void>
  regenerateMessage: (messageId: string, options?: { documentGroupId?: string | null; useWebSearch?: boolean; deepSearch?: boolean; maxIterations?: number; maxQueries?: number }) => Promise<void>
  removeMessage: (messageId: string) => void;
  
  // WebSocket management
  connectWebSocket: (sessionId: string) => Promise<void>
  disconnectWebSocket: () => void
}

export const useWritingStore = create<WritingState>((set, get) => ({
  // Initial state
  currentSession: null,
  currentDraft: null,
  messagesByChat: {},
  loadingStates: {},
  error: null,
  sessions: [],
  chats: [],
  activeChat: null,
  isLoading: false,
  isWebSocketConnected: false,
  agentStatus: {},

  // Basic setters
  setCurrentSession: (session) => set({ currentSession: session }),
  setCurrentDraft: (draft) => set({ currentDraft: draft }),
  setSessionLoading: (sessionId: string, loading: boolean) => {
    set((state) => ({
      loadingStates: {
        ...state.loadingStates,
        [sessionId]: loading
      }
    }))
  },
  getSessionLoading: (sessionId: string) => {
    const state = get()
    return state.loadingStates[sessionId] || false
  },
  clearError: () => set({ error: null }),
  setWebSocketConnected: (connected) => set({ isWebSocketConnected: connected }),
  setAgentStatus: (sessionId: string, status: string) => {
    set((state) => ({
      agentStatus: {
        ...state.agentStatus,
        [sessionId]: status
      }
    }))
  },
  getCurrentAgentStatus: () => {
    const state = get()
    const sessionId = state.currentSession?.id || state.activeChat?.id
    return sessionId ? (state.agentStatus[sessionId] || 'idle') : 'idle'
  },

  // Computed getters
  getCurrentMessages: () => {
    const state = get()
    const chatId = state.activeChat?.id || state.currentSession?.chat_id
    return chatId ? (state.messagesByChat[chatId] || []) : []
  },

  // Message management
  addMessage: (message) => {
    const state = get()
    const chatId = state.activeChat?.id || state.currentSession?.chat_id
    if (!chatId) return
    
    set((state) => ({
      messagesByChat: {
        ...state.messagesByChat,
        [chatId]: [...(state.messagesByChat[chatId] || []), message]
      }
    }))
  },

  clearMessages: async () => {
    const state = get()
    const chatId = state.activeChat?.id || state.currentSession?.chat_id
    
    if (!chatId) {
      // If no current chat, just clear UI
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId || 'default']: []
        }
      }))
      return
    }

    try {
      // Clear messages from backend database
      await writingApi.clearChatMessages(chatId)
      // Clear messages from UI
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: []
        }
      }))
    } catch (error) {
      console.error('Failed to clear chat messages:', error)
      // Still clear UI even if backend fails
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: []
        }
      }))
    }
  },

  removeMessage: async (messageId) => {
    const state = get()
    const chatId = state.activeChat?.id || state.currentSession?.chat_id
    
    if (!chatId) {
      // If no current chat, just remove from UI
      const currentMessages = state.getCurrentMessages()
      const filteredMessages = currentMessages.filter((msg) => msg.id !== messageId)
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId || 'default']: filteredMessages
        }
      }))
      return
    }

    try {
      // Delete message pair from backend database
      await writingApi.deleteMessagePair(chatId, messageId)
      // Remove message pair from UI - we need to find and remove the conversation pair
      const messages = state.getCurrentMessages()
      const messageIndex = messages.findIndex(m => m.id === messageId)
      
      if (messageIndex !== -1) {
        const targetMessage = messages[messageIndex]
        let messagesToRemove: string[] = []
        
        if (targetMessage.role === 'user') {
          // If user message clicked, remove user + following assistant message
          messagesToRemove.push(targetMessage.id)
          if (messageIndex + 1 < messages.length && messages[messageIndex + 1].role === 'assistant') {
            messagesToRemove.push(messages[messageIndex + 1].id)
          }
        } else {
          // If assistant message clicked, find preceding user message and remove both
          for (let i = messageIndex - 1; i >= 0; i--) {
            if (messages[i].role === 'user') {
              messagesToRemove.push(messages[i].id)
              break
            }
          }
          messagesToRemove.push(targetMessage.id)
        }
        
        const filteredMessages = messages.filter((msg) => !messagesToRemove.includes(msg.id))
        set((state) => ({
          messagesByChat: {
            ...state.messagesByChat,
            [chatId]: filteredMessages
          }
        }))
      }
    } catch (error) {
      console.error('Failed to delete message pair:', error)
      // Still remove from UI even if backend fails - just remove the clicked message
      const currentMessages = state.getCurrentMessages()
      const filteredMessages = currentMessages.filter((msg) => msg.id !== messageId)
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: filteredMessages
        }
      }))
    }
  },

  // Session management
  loadSessions: async () => {
    // Use a temporary loading state for session loading
    const tempSessionId = 'sessions_loading'
    const state = get()
    state.setSessionLoading(tempSessionId, true)
    set({ error: null })
    try {
      const sessions = await writingApi.getWritingSessions()
      set({ sessions })
      state.setSessionLoading(tempSessionId, false)
    } catch (error) {
      console.error('Failed to load writing sessions:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load writing sessions'
      })
      state.setSessionLoading(tempSessionId, false)
    }
  },

  createSession: async (sessionData) => {
    // Use a temporary loading state for session creation
    const tempSessionId = 'session_creating'
    const state = get()
    state.setSessionLoading(tempSessionId, true)
    set({ error: null })
    try {
      const newSession = await writingApi.createWritingSession(sessionData)
      
      set((state) => ({
        sessions: [newSession, ...state.sessions],
        currentSession: newSession
      }))
      
      state.setSessionLoading(tempSessionId, false)
      
      // Automatically load the draft for the new session
      try {
        await state.loadDraft(newSession.id)
      } catch (draftError) {
        console.error('Failed to load draft for new session:', draftError)
        // Don't fail session creation if draft loading fails
      }
      
      // Establish WebSocket connection for the new session
      try {
        await state.connectWebSocket(newSession.id)
        console.log('WebSocket connected for new session:', newSession.id)
      } catch (wsError) {
        console.error('Failed to connect WebSocket for new session:', wsError)
        // Don't fail session creation if WebSocket connection fails
      }
      
      return newSession
    } catch (error) {
      console.error('Failed to create writing session:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to create writing session'
      })
      state.setSessionLoading(tempSessionId, false)
      throw error
    }
  },

  selectSession: async (sessionId) => {
    const state = get()
    const session = state.sessions.find(s => s.id === sessionId)
    
    if (session) {
      // Disconnect from previous session's WebSocket
      state.disconnectWebSocket()
      
      // Clear messages for the current chat when switching sessions
      const chatId = session.chat_id
      set((state) => ({ 
        currentSession: session,
        currentDraft: null, // Clear current draft when switching sessions
        messagesByChat: chatId ? {
          ...state.messagesByChat,
          [chatId]: []
        } : state.messagesByChat
      }))
      
      // Load the draft for this session
      try {
        await state.loadDraft(sessionId)
      } catch (error) {
        console.error('Failed to load draft for selected session:', error)
      }
      
      // Connect to WebSocket for this session
      try {
        await state.connectWebSocket(sessionId)
      } catch (error) {
        console.error('Failed to connect to WebSocket for session:', error)
      }
    } else {
      throw new Error('Session not found')
    }
  },

  deleteSession: async (sessionId) => {
    try {
      await writingApi.deleteWritingSession(sessionId)
      
      set((state) => {
        const chatId = state.currentSession?.chat_id
        return {
          sessions: state.sessions.filter(session => session.id !== sessionId),
          currentSession: state.currentSession?.id === sessionId ? null : state.currentSession,
          currentDraft: state.currentSession?.id === sessionId ? null : state.currentDraft,
          messagesByChat: state.currentSession?.id === sessionId && chatId ? {
            ...state.messagesByChat,
            [chatId]: []
          } : state.messagesByChat
        }
      })
    } catch (error) {
      console.error('Failed to delete writing session:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to delete writing session'
      })
      throw error
    }
  },

  // Chat management (for writing chats)
  loadChats: async () => {
    set({ isLoading: true, error: null })
    try {
      // Import the API client
      const { apiClient } = await import('../../config/api')
      const response = await apiClient.get('/api/chats?chat_type=writing')
      set({ chats: response.data, isLoading: false })
    } catch (error) {
      console.error('Failed to load writing chats:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load writing chats',
        isLoading: false 
      })
    }
  },

  createChat: async (title = 'New Writing Chat') => {
    set({ isLoading: true, error: null })
    try {
      // Import the API client
      const { apiClient } = await import('../../config/api')
      const response = await apiClient.post('/api/chats', {
        title,
        chat_type: 'writing'
      })
      const newChat = response.data
      
      set((state) => ({
        chats: [newChat, ...state.chats],
        activeChat: newChat,
        messagesByChat: {
          ...state.messagesByChat,
          [newChat.id]: []
        },
        currentSession: null, // Clear current session
        currentDraft: null, // Clear current draft
        isLoading: false
      }))
      
      return newChat
    } catch (error) {
      console.error('Failed to create writing chat:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to create writing chat',
        isLoading: false 
      })
      throw error
    }
  },

  setActiveChat: async (chatId: string) => {
    const state = get()
    
    // Save current draft changes before switching chats
    if (typeof window !== 'undefined' && (window as any).saveCurrentDraftChanges) {
      console.log('Saving current draft changes before switching chats...')
      try {
        const saveSuccess = await (window as any).saveCurrentDraftChanges()
        if (!saveSuccess) {
          console.warn('Failed to save current draft changes, but continuing with chat switch')
        }
      } catch (error) {
        console.error('Error saving current draft changes:', error)
        // Continue with chat switch even if save fails
      }
    }
    
    // Check if we already have the chat
    const existingChat = state.chats.find(c => c.id === chatId)
    if (existingChat) {
      // Clear current state first to ensure clean slate
      set((state) => ({ 
        activeChat: existingChat, 
        error: null,
        messagesByChat: {
          ...state.messagesByChat,
          [existingChat.id]: []
        },
        currentSession: null, 
        currentDraft: null,
        // Clear agent status for the new chat to prevent spinner from following
        agentStatus: {
          ...state.agentStatus,
          [existingChat.id]: 'idle'
        }
      }))
      
      // Load chat messages and writing session
      try {
        // Import the API client
        const { apiClient } = await import('../../config/api')
        
        // Load chat messages
        const messagesResponse = await apiClient.get(`/api/chats/${chatId}/messages`)
        const convertedMessages: WritingMessageWithSources[] = messagesResponse.data.map((msg: any) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: ensureDate(msg.created_at),
          sources: msg.sources || []
        }))
        set((state) => ({
          messagesByChat: {
            ...state.messagesByChat,
            [chatId]: convertedMessages
          }
        }))

        // Try to load writing session for this chat
        try {
          const sessionResponse = await apiClient.get(`/api/writing/sessions/by-chat/${chatId}`)
          const session = sessionResponse.data
          set({ currentSession: session })
          
          // Load current draft if exists
          if (session.current_draft) {
            set({ currentDraft: session.current_draft })
          } else {
            // Try to load/create draft
            try {
              const draftResponse = await apiClient.get(`/api/writing/sessions/${session.id}/draft`)
              set({ currentDraft: draftResponse.data })
            } catch (draftError) {
              console.error('Failed to load/create draft:', draftError)
            }
          }
        } catch (sessionError) {
          console.log('No writing session found for chat, will create when needed')
        }
      } catch (error) {
        console.error('Failed to load chat data:', error)
        set({ error: error instanceof Error ? error.message : 'Failed to load chat data' })
      }
    } else {
      set((state) => ({ 
        error: 'Chat not found', 
        activeChat: null, 
        messagesByChat: {
          ...state.messagesByChat,
          ['default']: []
        },
        currentSession: null, 
        currentDraft: null 
      }))
    }
  },

  deleteChat: async (chatId: string) => {
    try {
      // Import the API client
      const { apiClient } = await import('../../config/api')
      await apiClient.delete(`/api/chats/${chatId}`)
      
      set((state) => {
        const updatedChats = state.chats.filter((chat) => chat.id !== chatId)
        const isActiveChat = state.activeChat?.id === chatId

        return {
          chats: updatedChats,
          // Clear active chat if it's the one being deleted
          activeChat: isActiveChat ? null : state.activeChat,
          // Clear current session and messages if deleting active chat
          currentSession: isActiveChat ? null : state.currentSession,
          currentDraft: isActiveChat ? null : state.currentDraft,
          // Clear messages for the deleted chat
          messagesByChat: {
            ...state.messagesByChat,
            [chatId]: []
          },
          // Clear agent status for the deleted chat
          agentStatus: {
            ...state.agentStatus,
            [chatId]: 'idle'
          }
        }
      })
    } catch (error) {
      console.error('Failed to delete writing chat:', error)
      set({ error: error instanceof Error ? error.message : 'Failed to delete writing chat' })
      throw error
    }
  },

  // Draft management
  loadDraft: async (sessionId: string) => {
    const state = get()
    state.setSessionLoading(sessionId, true)
    set({ error: null })
    try {
      const draft = await writingApi.getSessionDraft(sessionId)
      set({ currentDraft: draft })
      state.setSessionLoading(sessionId, false)
      
      // Also load messages for this session if we don't have any
      const currentMessages = state.getCurrentMessages()
      if (currentMessages.length === 0) {
        try {
          const chatId = state.activeChat?.id || state.currentSession?.chat_id
          if (chatId) {
            // Use the correct chat messages endpoint instead of the non-existent writing endpoint
            const { apiClient } = await import('../../config/api')
            const messagesResponse = await apiClient.get(`/api/chats/${chatId}/messages`)
            // Convert API messages to proper format with timezone-aware timestamps
            const convertedMessages: WritingMessageWithSources[] = messagesResponse.data.map((msg: any) => ({
              id: msg.id,
              role: msg.role,
              content: msg.content,
              timestamp: ensureDate(msg.created_at),
              sources: msg.sources || []
            }))
            set((state) => ({
              messagesByChat: {
                ...state.messagesByChat,
                [chatId]: convertedMessages
              }
            }))
          }
        } catch (messageError) {
          console.error('Failed to load session messages:', messageError)
          // Don't fail the whole operation if messages can't be loaded
        }
      }
    } catch (error) {
      console.error('Failed to load draft:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load draft'
      })
      state.setSessionLoading(sessionId, false)
    }
  },

  saveDraftChanges: async (content: string, title?: string) => {
    const state = get()
    if (!state.currentDraft || !state.currentSession) {
      console.log('No current draft or session to save changes to')
      return
    }

    try {
      console.log('Saving draft changes from store...')
      await writingApi.updateSessionDraft(state.currentSession.id, {
        title: title || state.currentDraft.title,
        content: content,
      })
      
      // Update the store optimistically
      set({
        currentDraft: { 
          ...state.currentDraft, 
          content, 
          title: title || state.currentDraft.title 
        }
      })
      
      console.log('Draft changes saved successfully from store')
    } catch (error) {
      console.error('Failed to save draft changes from store:', error)
      throw error
    }
  },

  // Enhanced chat
  sendMessage: async (message: string, options?: { documentGroupId?: string | null; useWebSearch?: boolean; deepSearch?: boolean; maxIterations?: number; maxQueries?: number }) => {
    const state = get()
    let session = state.currentSession

    // If no session, create one
    if (!session) {
      try {
        // Check if we have an active chat that needs a session
        if (state.activeChat) {
          // Create a session for the existing active chat
          const { apiClient } = await import('../../config/api')
          const sessionResponse = await apiClient.post('/api/writing/sessions', {
            name: state.activeChat.title,
            chat_id: state.activeChat.id,
            document_group_id: options?.documentGroupId,
            web_search_enabled: options?.useWebSearch
          })
          session = sessionResponse.data
          
          // Update the store with the new session
          set({ currentSession: session })
          
          // Load the draft for this session
          try {
            await state.loadDraft(session!.id)
          } catch (draftError) {
            console.error('Failed to load draft for new session:', draftError)
          }
          
          // Establish WebSocket connection for the new session
          try {
            await state.connectWebSocket(session!.id)
            console.log('WebSocket connected for existing chat session:', session!.id)
          } catch (wsError) {
            console.error('Failed to connect WebSocket for new session:', wsError)
          }
        } else {
          // No active chat, create a completely new session (which will create a new chat)
          session = await state.createSession({
            name: 'New Writing Chat',
            document_group_id: options?.documentGroupId,
            web_search_enabled: options?.useWebSearch
          })
        }
      } catch (error) {
        console.error('Failed to auto-create session:', error)
        // Add error message to UI
        const errorMessage: WritingMessageWithSources = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Failed to start a new session. Please try creating one manually.',
          timestamp: ensureDate(new Date()),
          sources: []
        }
        state.addMessage(errorMessage)
        return
      }
    }

    // Ensure we have a valid session at this point
    if (!session) {
      throw new Error('Failed to create or find a valid session')
    }

    // Ensure WebSocket is connected for this session
    if (!state.isWebSocketConnected) {
      try {
        console.log('Establishing WebSocket connection before sending message...')
        await state.connectWebSocket(session.id)
      } catch (wsError) {
        console.error('Failed to establish WebSocket connection:', wsError)
        // Continue without WebSocket - the message will still work, just no real-time updates
      }
    }

    // Add user message with timezone-aware timestamp
    const userMessage: WritingMessageWithSources = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: ensureDate(new Date()),
      sources: []
    }
    
    state.addMessage(userMessage)
    
    // Set loading for current session
    const loadingId = session.id
    if (loadingId) {
      state.setSessionLoading(loadingId, true)
    }
    set({ error: null })
    
    try {
      // Ensure we have a current draft - if not, load/create one
      let currentDraft = state.currentDraft
      if (!currentDraft) {
        console.log('No current draft found, loading/creating one...')
        await state.loadDraft(session.id)
        currentDraft = get().currentDraft
        
        if (!currentDraft) {
          throw new Error('Failed to load or create draft')
        }
      }
      
      // Send to enhanced writing chat API with tool options
      const response = await writingApi.sendWritingChatMessage({
        message,
        draft_id: currentDraft.id,
        operation_mode: 'balanced',
        document_group_id: options?.documentGroupId,
        use_web_search: options?.useWebSearch,
        deep_search: options?.deepSearch,
        max_search_iterations: options?.maxIterations,
        max_decomposed_queries: options?.maxQueries
      })
      
      console.log('Received response from writing API:', response)
      
      // Add the assistant response
      const assistantMessage: WritingMessageWithSources = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: ensureDate(new Date()),
        sources: response.sources || []
      }
      
      console.log('Adding assistant message to UI:', assistantMessage)
      state.addMessage(assistantMessage)
      
      // Clear loading state and reset agent status
      if (loadingId) {
        state.setSessionLoading(loadingId, false)
        // Reset agent status to idle after successful response
        state.setAgentStatus(loadingId, 'idle')
      }
      
    } catch (error: any) {
      console.error('Failed to send message:', error)
      
      // Check if it's a 504 Gateway Timeout
      if (error?.response?.status === 504) {
        console.log('Received 504 Gateway Timeout - checking if response was processed...')
        
        // Wait a moment for the backend to finish processing
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        // Try to reload messages to see if the response was actually saved
        try {
          const chatId = state.currentSession?.chat_id || state.activeChat?.id
          if (chatId) {
            const { apiClient } = await import('../../config/api')
            const messagesResponse = await apiClient.get(`/api/chats/${chatId}/messages`)
            const messages = messagesResponse.data
            
            // Check if we have a new assistant message after our user message
            const lastAssistantMessage = messages
              .filter((msg: any) => msg.role === 'assistant')
              .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]
            
            if (lastAssistantMessage && !state.getCurrentMessages().find(m => m.content === lastAssistantMessage.content)) {
              // We found a new assistant message that wasn't in our UI - add it
              const assistantMessage: WritingMessageWithSources = {
                id: lastAssistantMessage.id || (Date.now() + 1).toString(),
                role: 'assistant',
                content: lastAssistantMessage.content,
                timestamp: ensureDate(new Date(lastAssistantMessage.created_at)),
                sources: lastAssistantMessage.sources || []
              }
              
              console.log('Found completed response despite 504 timeout, adding to UI')
              state.addMessage(assistantMessage)
              
              // Clear loading state - request completed successfully
              if (loadingId) {
                state.setSessionLoading(loadingId, false)
                // Reset agent status to idle after successful response
                state.setAgentStatus(loadingId, 'idle')
              }
              return // Exit without showing error
            }
          }
        } catch (refreshError) {
          console.error('Failed to check for completed response:', refreshError)
        }
        
        // If we couldn't find a completed response, show timeout-specific error
        const errorMessage: WritingMessageWithSources = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'The request timed out due to proxy limits, but may still be processing. Please refresh the page in a moment to see if the response completed.',
          timestamp: ensureDate(new Date()),
          sources: []
        }
        
        state.addMessage(errorMessage)
        set({ 
          error: 'Request timed out - please check your proxy timeout settings'
        })
      } else {
        // Handle other errors normally
        const errorMessage: WritingMessageWithSources = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Sorry, I encountered an error while processing your message. Please try again.',
          timestamp: ensureDate(new Date()),
          sources: []
        }
        
        state.addMessage(errorMessage)
        set({ 
          error: error instanceof Error ? error.message : 'Failed to send message'
        })
      }
      
      // Clear loading state and reset agent status
      if (loadingId) {
        state.setSessionLoading(loadingId, false)
        // Reset agent status to idle on error
        state.setAgentStatus(loadingId, 'idle')
      }
    }
  },

  regenerateMessage: async (messageId: string, options?: { documentGroupId?: string | null; useWebSearch?: boolean; deepSearch?: boolean; maxIterations?: number; maxQueries?: number }) => {
    const state = get()
    const messages = state.getCurrentMessages()
    const messageIndex = messages.findIndex(m => m.id === messageId)

    if (messageIndex === -1) {
      throw new Error('Message not found')
    }

    // Find the user message to regenerate from
    let userMessageIndex = messageIndex
    let userMessage = messages[messageIndex]
    let assistantMessageToDelete = messages[messageIndex]
    
    if (userMessage.role !== 'user') {
      // If clicked on assistant message, find the preceding user message
      const precedingUserIndex = messages.slice(0, messageIndex).reverse().findIndex(m => m.role === 'user')
      if (precedingUserIndex === -1) {
        throw new Error('No user message found to regenerate from')
      }
      userMessageIndex = messageIndex - 1 - precedingUserIndex
      userMessage = messages[userMessageIndex]
      assistantMessageToDelete = messages[messageIndex]
    } else {
      // If clicked on user message, find the following assistant message to delete
      if (messageIndex + 1 < messages.length && messages[messageIndex + 1].role === 'assistant') {
        assistantMessageToDelete = messages[messageIndex + 1]
      } else {
        assistantMessageToDelete = userMessage // fallback
      }
    }

    try {
      const chatId = state.activeChat?.id || state.currentSession?.chat_id
      if (!chatId) {
        throw new Error('No current chat available')
      }

      // Delete messages from the backend starting from the assistant message we want to regenerate
      await writingApi.deleteMessagesFromPoint(chatId, assistantMessageToDelete.id)
      
      // Update UI to show only messages up to the user message (excluding the assistant response)
      const messagesUpToUser = messages.slice(0, userMessageIndex + 1)
      set((state) => ({
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: messagesUpToUser
        },
        error: null
      }))
      
      // Set loading for current session or active chat
      const loadingId = state.currentSession?.id || state.activeChat?.id
      if (loadingId) {
        state.setSessionLoading(loadingId, true)
      }

      let currentDraft = state.currentDraft
      if (!currentDraft && state.currentSession) {
        await state.loadDraft(state.currentSession.id)
        currentDraft = get().currentDraft
        if (!currentDraft) {
          throw new Error('Failed to load or create draft')
        }
      }

      // Send the regeneration request
      const response = await writingApi.sendWritingChatMessage({
        message: userMessage.content,
        draft_id: currentDraft!.id,
        operation_mode: 'balanced',
        document_group_id: options?.documentGroupId,
        use_web_search: options?.useWebSearch,
        deep_search: options?.deepSearch,
        max_search_iterations: options?.maxIterations,
        max_decomposed_queries: options?.maxQueries
      })

      // Add the new assistant response
      const assistantMessage: WritingMessageWithSources = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: ensureDate(new Date()),
        sources: response.sources || []
      }

      state.addMessage(assistantMessage)
      
      // Clear loading state and reset agent status
      if (loadingId) {
        state.setSessionLoading(loadingId, false)
        // Reset agent status to idle after successful response
        state.setAgentStatus(loadingId, 'idle')
      }

    } catch (error: any) {
      console.error('Failed to regenerate message:', error)

      // Check if it's a 504 Gateway Timeout
      if (error?.response?.status === 504) {
        console.log('Received 504 Gateway Timeout during regeneration - checking if response was processed...')
        
        // Wait a moment for the backend to finish processing
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        // Try to reload messages to see if the regeneration completed
        try {
          const chatId = state.currentSession?.chat_id || state.activeChat?.id
          if (chatId) {
            const { apiClient } = await import('../../config/api')
            const messagesResponse = await apiClient.get(`/api/chats/${chatId}/messages`)
            const messages = messagesResponse.data
            
            // Check if we have a new assistant message
            const lastAssistantMessage = messages
              .filter((msg: any) => msg.role === 'assistant')
              .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]
            
            if (lastAssistantMessage && !state.getCurrentMessages().find(m => m.content === lastAssistantMessage.content)) {
              // We found a new assistant message that wasn't in our UI - add it
              const assistantMessage: WritingMessageWithSources = {
                id: lastAssistantMessage.id || (Date.now() + 1).toString(),
                role: 'assistant',
                content: lastAssistantMessage.content,
                timestamp: ensureDate(new Date(lastAssistantMessage.created_at)),
                sources: lastAssistantMessage.sources || []
              }
              
              console.log('Found completed regeneration despite 504 timeout, adding to UI')
              state.addMessage(assistantMessage)
              
              // Clear loading state - regeneration completed successfully
              const loadingId = state.currentSession?.id || state.activeChat?.id
              if (loadingId) {
                state.setSessionLoading(loadingId, false)
                // Reset agent status to idle after successful response
                state.setAgentStatus(loadingId, 'idle')
              }
              return // Exit without showing error
            }
          }
        } catch (refreshError) {
          console.error('Failed to check for completed regeneration:', refreshError)
        }
        
        // If we couldn't find a completed response, show timeout-specific error
        const errorMessage: WritingMessageWithSources = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'The regeneration request timed out due to proxy limits, but may still be processing. Please refresh the page in a moment.',
          timestamp: ensureDate(new Date()),
          sources: []
        }
        
        state.addMessage(errorMessage)
        set({
          error: 'Regeneration timed out - please check your proxy timeout settings'
        })
      } else {
        // Handle other errors normally
        const errorMessage: WritingMessageWithSources = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Sorry, I encountered an error while regenerating the response. Please try again.',
          timestamp: ensureDate(new Date()),
          sources: []
        }

        state.addMessage(errorMessage)
        set({
          error: error instanceof Error ? error.message : 'Failed to regenerate message'
        })
      }
      
      // Clear loading state and reset agent status
      const loadingId = state.currentSession?.id || state.activeChat?.id
      if (loadingId) {
        state.setSessionLoading(loadingId, false)
        // Reset agent status to idle on error
        state.setAgentStatus(loadingId, 'idle')
      }
    }
  },

  // WebSocket management
  connectWebSocket: async (sessionId: string) => {
    try {
      // Import the dedicated writing WebSocket service
      const { writingWebSocketService } = await import('./services/writingWebSocketService')
      
      // Connect to the writing session WebSocket
      await writingWebSocketService.connectToSession(sessionId)
      
      // Set up WebSocket event handlers
      const unsubscribe = writingWebSocketService.onStatusUpdate((message: any) => {
        const state = get()
        
        // Only handle messages for our current session
        if (message.session_id !== sessionId) {
          return
        }
        
        switch (message.type) {
          case 'connection_established':
            state.setWebSocketConnected(true)
            console.log('Writing WebSocket connected for session:', sessionId)
            break
            
          case 'agent_status':
            if (message.status) {
              // If we have details, combine them with the status for a more informative message
              let statusText = message.status
              if (message.details) {
                statusText = message.details  // Use details as the full message
                console.log(`Agent status: ${message.status} - ${message.details}`)
              } else {
                console.log(`Agent status: ${message.status}`)
              }
              state.setAgentStatus(sessionId, statusText)
              
              // Reset to idle after completion to ensure spinner disappears
              if (message.status === 'complete') {
                setTimeout(() => {
                  const currentState = get()
                  // Only reset if we're still in complete status (not overridden by new message)
                  const currentAgentStatus = currentState.getCurrentAgentStatus()
                  if (currentAgentStatus === 'complete') {
                    state.setAgentStatus(sessionId, 'idle')
                  }
                }, 1000) // 1 second delay to show completion briefly
              }
            }
            break
            
            
          case 'draft_content_update':
            // Only refresh the draft if no user is currently editing
            // This prevents cursor jumping issues in the editor
            if (state.currentSession?.id === sessionId) {
              // Check if the editor is currently being used
              const editorContainer = document.querySelector('.editor-container');
              const isEditorFocused = editorContainer && editorContainer.contains(document.activeElement);
              
              if (!isEditorFocused) {
                console.log('Refreshing draft content from WebSocket update');
                state.loadDraft(sessionId).catch(console.error);
              } else {
                console.log('Skipping draft refresh - user is actively editing');
              }
            }
            break
            
          case 'chat_title_update':
            // Update the chat title in the sessions list and reload sessions
            if (message.chat_id && message.title) {
              // Update the session name in the current sessions list
              set((currentState) => ({
                sessions: currentState.sessions.map(session => 
                  session.chat_id === message.chat_id 
                    ? { ...session, name: message.title } as WritingSession
                    : session
                ),
                // Also update current session if it matches
                currentSession: currentState.currentSession?.chat_id === message.chat_id && currentState.currentSession
                  ? { ...currentState.currentSession, name: message.title } as WritingSession
                  : currentState.currentSession
              }))
              
              console.log(`Updated chat title for ${message.chat_id} to: ${message.title}`)
              
              // Dispatch a custom event to notify the sidebar
              window.dispatchEvent(new CustomEvent('writingChatTitleUpdate', {
                detail: {
                  chatId: message.chat_id,
                  title: message.title
                }
              }))
            }
            break
            
          case 'stats_update':
            // Handle real-time stats updates
            if (message.session_id === sessionId && message.data) {
              console.log('Received stats update via WebSocket in store:', message.data)
              // Dispatch a custom event to notify the stats component
              window.dispatchEvent(new CustomEvent('writingStatsUpdate', {
                detail: {
                  sessionId: message.session_id,
                  stats: message.data
                }
              }))
            }
            break
            
          default:
            console.log('Unhandled writing WebSocket update:', message)
        }
      })
      
      // Store the unsubscribe function for cleanup
      ;(writingWebSocketService as any)._currentWritingUnsubscribe = unsubscribe
      
      // Check if connected
      if (writingWebSocketService.isConnected()) {
        set({ isWebSocketConnected: true })
      }
      
    } catch (error) {
      console.error('Failed to connect to writing WebSocket:', error)
      set({ isWebSocketConnected: false })
    }
  },

  disconnectWebSocket: () => {
    // Import and disconnect the writing WebSocket service
    import('./services/writingWebSocketService').then(({ writingWebSocketService }) => {
      // Clean up the subscription
      const unsubscribe = (writingWebSocketService as any)._currentWritingUnsubscribe
      if (unsubscribe) {
        unsubscribe()
        ;(writingWebSocketService as any)._currentWritingUnsubscribe = null
      }
      
      writingWebSocketService.disconnect()
    }).catch(console.error)
    
    set({ isWebSocketConnected: false, agentStatus: {} })
  }
}))
