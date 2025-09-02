import { create } from 'zustand'
import * as chatApi from './api'
import { ensureDate } from '../../utils/timezone'

interface Message {
  id: string
  content: string
  role: 'user' | 'assistant'
  timestamp: Date
}

interface Chat {
  id: string
  title: string
  messages: Message[]
  missionId?: string // Associate chat with a mission
  createdAt: Date
  updatedAt: Date
  settings?: {
    document_group_id?: string | null
    use_web_search?: boolean
    [key: string]: any
  }
}

interface ChatState {
  chats: Chat[]
  activeChat: Chat | null
  isLoading: boolean
  error: string | null
  // Pagination state
  currentPage: number
  totalPages: number
  totalChats: number
  pageSize: number
  searchQuery: string
  hasMore: boolean
  
  // Actions
  loadChats: (page?: number, search?: string) => Promise<void>
  loadMoreChats: () => Promise<void>
  searchChats: (query: string) => Promise<void>
  createChat: (title?: string) => Promise<Chat>
  setActiveChat: (chatId: string) => Promise<void>
  addMessage: (chatId: string, message: Omit<Message, 'id' | 'timestamp'>) => Promise<void>
  updateChatTitle: (chatId: string, title: string) => Promise<void>
  updateChat: (chatId: string, data: chatApi.UpdateChatRequest) => Promise<void>
  associateMissionWithChat: (chatId: string, missionId: string) => void
  deleteChat: (chatId: string) => Promise<void>
  clearChats: () => void
  clearError: () => void
}

// Helper function to convert API chat to store chat format
const convertApiChatToStoreChat = (apiChat: chatApi.Chat): Chat => {
  // console.log('Converting API chat to store chat:', {
  //   chatId: apiChat.id,
  //   messageTimestamps: apiChat.messages.map(msg => ({
  //     original: msg.created_at,
  //     converted: ensureDate(msg.created_at),
  //     convertedISO: ensureDate(msg.created_at).toISOString()
  //   }))
  // });
  
  return {
    id: apiChat.id,
    title: apiChat.title,
    messages: apiChat.messages.map(msg => {
      const timestamp = ensureDate(msg.created_at);
      // console.log(`Message ${msg.id} timestamp:`, {
      //   original: msg.created_at,
      //   converted: timestamp,
      //   convertedISO: timestamp.toISOString()
      // });
      return {
        id: msg.id,
        content: msg.content,
        role: msg.role,
        timestamp: timestamp
      };
    }),
    missionId: apiChat.missions.length > 0 ? apiChat.missions[0].id : undefined,
    createdAt: ensureDate(apiChat.created_at),
    updatedAt: ensureDate(apiChat.updated_at),
    settings: apiChat.settings
  }
}

// Helper function to convert API chat summary to store chat format
const convertApiChatSummaryToStoreChat = (apiChatSummary: chatApi.ChatSummary): Chat => {
  return {
    id: apiChatSummary.id,
    title: apiChatSummary.title,
    messages: [], // Messages will be loaded when chat is selected
    missionId: undefined, // Will be loaded when chat is selected
    createdAt: ensureDate(apiChatSummary.created_at),
    updatedAt: ensureDate(apiChatSummary.updated_at)
  }
}

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  activeChat: null,
  isLoading: false,
  error: null,
  // Pagination state
  currentPage: 1,
  totalPages: 0,
  totalChats: 0,
  pageSize: 20,
  searchQuery: '',
  hasMore: false,

  clearError: () => set({ error: null }),

  loadChats: async (page = 1, search = '') => {
    set({ isLoading: true, error: null })
    try {
      const response = await chatApi.getUserChats(page, 20, search || undefined)
      
      // Ensure response.items is an array
      if (!response || !Array.isArray(response.items)) {
        console.error('Invalid response from getUserChats:', response)
        set({ 
          chats: [],
          isLoading: false,
          error: 'Invalid response format from server'
        })
        return
      }
      
      const chats = response.items.map(convertApiChatSummaryToStoreChat)
      
      set({ 
        chats: page === 1 ? chats : [...get().chats, ...chats],
        currentPage: response.page,
        totalPages: response.total_pages,
        totalChats: response.total,
        hasMore: response.page < response.total_pages,
        searchQuery: search,
        isLoading: false 
      })
    } catch (error) {
      console.error('Failed to load chats:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load chats',
        isLoading: false,
        chats: [] // Ensure chats is always an array
      })
    }
  },

  loadMoreChats: async () => {
    const state = get()
    if (!state.hasMore || state.isLoading) return
    
    await state.loadChats(state.currentPage + 1, state.searchQuery)
  },

  searchChats: async (query: string) => {
    await get().loadChats(1, query)
  },

  createChat: async (title = 'New Chat') => {
    set({ isLoading: true, error: null })
    try {
      const apiChat = await chatApi.createChat({ title })
      const newChat = convertApiChatToStoreChat(apiChat)
      
      set((state) => ({
        chats: [newChat, ...state.chats],
        activeChat: newChat,
        isLoading: false
      }))
      
      return newChat
    } catch (error) {
      console.error('Failed to create chat:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to create chat',
        isLoading: false 
      })
      throw error
    }
  },

  setActiveChat: async (chatId: string) => {
    const state = get()
    
    // Check if we already have the full chat data
    const existingChat = state.chats.find(c => c.id === chatId)
    if (existingChat && existingChat.messages.length > 0) {
      set({ activeChat: existingChat, error: null })
      return
    }

    // If we have a chat summary but no messages, set it as active first to prevent flashing
    if (existingChat) {
      set({ activeChat: existingChat, isLoading: true, error: null })
    } else {
      set({ isLoading: true, error: null })
    }

    try {
      // Load full chat data from API
      const apiChat = await chatApi.getChat(chatId)
      const fullChat = convertApiChatToStoreChat(apiChat)
      
      // Update the chat in the list and set as active
      set((state) => {
        const updatedChats = state.chats.map(chat => 
          chat.id === chatId ? fullChat : chat
        )
        return {
          chats: updatedChats,
          activeChat: fullChat,
          isLoading: false
        }
      })
    } catch (error) {
      console.error('Failed to load chat:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load chat',
        isLoading: false,
        activeChat: null
      })
    }
  },

  addMessage: async (chatId: string, message: Omit<Message, 'id' | 'timestamp'>) => {
    try {
      // Add message to database
      const apiMessage = await chatApi.addMessageToChat(chatId, {
        content: message.content,
        role: message.role
      })

      const newMessage: Message = {
        id: apiMessage.id,
        content: apiMessage.content,
        role: apiMessage.role,
        timestamp: ensureDate(apiMessage.created_at || new Date())
      }

      // Update local state
      set((state) => {
        const updatedChats = state.chats.map((chat) => {
          if (chat.id === chatId) {
            const updatedChat = {
              ...chat,
              messages: [...chat.messages, newMessage],
              // Don't update updatedAt when adding messages - keep original timestamp
            }
            return updatedChat
          }
          return chat
        })

        // activeChat should reference the same object from updatedChats, not a separate copy
        const activeChat = state.activeChat?.id === chatId 
          ? updatedChats.find(c => c.id === chatId) || state.activeChat
          : state.activeChat

        return {
          chats: updatedChats,
          activeChat,
        }
      })
    } catch (error) {
      console.error('Failed to add message:', error)
      set({ error: error instanceof Error ? error.message : 'Failed to add message' })
      throw error
    }
  },

  updateChatTitle: async (chatId: string, title: string) => {
    try {
      // Update title in database
      await chatApi.updateChat(chatId, { title })

      // Update local state - only update the title, preserve existing messages and other data
      set((state) => {
        const updatedChats = state.chats.map((chat) =>
          chat.id === chatId 
            ? { ...chat, title }  // Don't update timestamp, just the title
            : chat
        )

        const activeChat = state.activeChat?.id === chatId
          ? { ...state.activeChat, title }  // Don't update timestamp, just the title
          : state.activeChat

        return {
          chats: updatedChats,
          activeChat,
        }
      })
    } catch (error) {
      console.error('Failed to update chat title:', error)
      set({ error: error instanceof Error ? error.message : 'Failed to update chat title' })
      throw error
    }
  },

  updateChat: async (chatId: string, data: chatApi.UpdateChatRequest) => {
    try {
      console.log('Store: Updating chat', chatId, 'with data:', data)
      
      // Update chat in database
      const updatedChatFromBackend = await chatApi.updateChat(chatId, data)
      console.log('Store: Backend returned updated chat:', updatedChatFromBackend)
      
      // Convert backend response to store format
      const convertedChat = convertApiChatToStoreChat(updatedChatFromBackend)
      console.log('Store: Converted chat:', convertedChat)

      // Update local state with the converted chat from backend
      set((state: ChatState) => {
        const updatedChats = state.chats.map((chat: Chat) => {
          if (chat.id === chatId) {
            // Use the converted chat from backend but preserve messages if not included
            const updatedChat = {
              ...convertedChat,
              messages: convertedChat.messages.length > 0 ? convertedChat.messages : chat.messages
            }
            console.log('Store: Using updated chat:', updatedChat)
            return updatedChat
          }
          return chat
        })

        // Update activeChat if it's the one being updated
        const activeChat = state.activeChat?.id === chatId
          ? updatedChats.find((c: Chat) => c.id === chatId) || null
          : state.activeChat

        console.log('Store: Updated activeChat:', activeChat)

        return {
          chats: updatedChats,
          activeChat,
        }
      })
      
      console.log('Store: Chat update completed successfully')
    } catch (error) {
      console.error('Store: Failed to update chat:', error)
      set({ error: error instanceof Error ? error.message : 'Failed to update chat' })
      throw error
    }
  },

  associateMissionWithChat: (chatId: string, missionId: string) => {
    // This is a local state update - the association is handled by the backend
    // when missions are created through the chat API
    set((state: ChatState) => {
      const updatedChats = state.chats.map((chat: Chat) =>
        chat.id === chatId
          ? { ...chat, missionId }  // Don't update updatedAt - this is just a local state association
          : chat
      )

      const activeChat = state.activeChat?.id === chatId
        ? updatedChats.find((c: Chat) => c.id === chatId) || null
        : state.activeChat

      return {
        chats: updatedChats,
        activeChat,
      }
    })
  },

  deleteChat: async (chatId: string) => {
    try {
      // Delete from database
      await chatApi.deleteChat(chatId)

      // Update local state
      set((state: ChatState) => {
        const updatedChats = state.chats.filter((chat: Chat) => chat.id !== chatId)
        const activeChat = state.activeChat?.id === chatId ? null : state.activeChat

        return {
          chats: updatedChats,
          activeChat,
        }
      })
    } catch (error) {
      console.error('Failed to delete chat:', error)
      set({ error: error instanceof Error ? error.message : 'Failed to delete chat' })
      throw error
    }
  },

  clearChats: () => {
    set({
      chats: [],
      activeChat: null,
      error: null
    })
  },
}))
