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
}

interface ChatState {
  chats: Chat[]
  activeChat: Chat | null
  isLoading: boolean
  error: string | null
  
  // Actions
  loadChats: () => Promise<void>
  createChat: (title?: string) => Promise<Chat>
  setActiveChat: (chatId: string) => Promise<void>
  addMessage: (chatId: string, message: Omit<Message, 'id' | 'timestamp'>) => Promise<void>
  updateChatTitle: (chatId: string, title: string) => Promise<void>
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
    updatedAt: ensureDate(apiChat.updated_at)
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

  clearError: () => set({ error: null }),

  loadChats: async () => {
    set({ isLoading: true, error: null })
    try {
      const chatSummaries = await chatApi.getUserChats()
      const chats = chatSummaries.map(convertApiChatSummaryToStoreChat)
      set({ chats, isLoading: false })
    } catch (error) {
      console.error('Failed to load chats:', error)
      set({ 
        error: error instanceof Error ? error.message : 'Failed to load chats',
        isLoading: false 
      })
    }
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
              updatedAt: ensureDate(new Date()),
            }
            return updatedChat
          }
          return chat
        })

        // Ensure activeChat is also updated with the new message
        const activeChat = state.activeChat?.id === chatId 
          ? {
              ...state.activeChat,
              messages: [...state.activeChat.messages, newMessage],
              updatedAt: ensureDate(new Date()),
            }
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
            ? { ...chat, title, updatedAt: ensureDate(new Date()) }
            : chat
        )

        const activeChat = state.activeChat?.id === chatId
          ? { ...state.activeChat, title, updatedAt: ensureDate(new Date()) }
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

  associateMissionWithChat: (chatId: string, missionId: string) => {
    // This is a local state update - the association is handled by the backend
    // when missions are created through the chat API
    set((state) => {
      const updatedChats = state.chats.map((chat) =>
        chat.id === chatId
          ? { ...chat, missionId, updatedAt: ensureDate(new Date()) }
          : chat
      )

      const activeChat = state.activeChat?.id === chatId
        ? updatedChats.find(c => c.id === chatId) || null
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
      set((state) => {
        const updatedChats = state.chats.filter((chat) => chat.id !== chatId)
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
