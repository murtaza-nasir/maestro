import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiClient } from '../../config/api'

interface User {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
  role: string
  user_type: string
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  csrfToken: string | null
  accessToken: string | null  // Add access token for WebSocket connections
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  setCsrfToken: (token: string) => void
  setAccessToken: (token: string) => void
  getAccessToken: () => string | null
  getCsrfToken: () => string | null
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      csrfToken: null,
      accessToken: null,

      login: async (username: string, password: string, rememberMe?: boolean) => {
        try {
          // Create form data for OAuth2PasswordRequestForm
          const formData = new FormData()
          formData.append('username', username)
          formData.append('password', password)
          
          const headers: Record<string, string> = {
            'Content-Type': 'application/x-www-form-urlencoded',
          }
          
          // Add remember me header if requested
          if (rememberMe) {
            headers['X-Remember-Me'] = 'true'
          }
          
          const response = await apiClient.post('/api/auth/login', formData, {
            headers,
          })
          
          const { csrf_token, access_token } = response.data
          
          // Store access token in localStorage for WebSocket connections
          if (access_token) {
            localStorage.setItem('access_token', access_token)
          }
          
          // Get user info after successful login
          const userResponse = await apiClient.get('/api/auth/me')
          
          set({
            user: userResponse.data,
            isAuthenticated: true,
            csrfToken: csrf_token,
            accessToken: access_token || null,
          })
          
          // Load user settings immediately after login
          try {
            const { useSettingsStore } = await import('./components/SettingsStore')
            const settingsStore = useSettingsStore.getState()
            await settingsStore.loadSettings()
          } catch (error) {
            console.error('Failed to load settings after login:', error)
          }
        } catch (error) {
          console.error('Login failed:', error)
          throw error
        }
      },

      register: async (username: string, password: string) => {
        try {
          // First register the user
          const registerResponse = await apiClient.post('/api/auth/register', {
            username,
            password,
          })
          
          // Then log them in to get the session and CSRF token
          const formData = new FormData()
          formData.append('username', username)
          formData.append('password', password)
          
          const loginResponse = await apiClient.post('/api/auth/login', formData, {
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
          })
          
          const { csrf_token, access_token } = loginResponse.data
          
          // Store access token in localStorage for WebSocket connections
          if (access_token) {
            localStorage.setItem('access_token', access_token)
          }
          
          set({
            user: registerResponse.data,
            isAuthenticated: true,
            csrfToken: csrf_token,
            accessToken: access_token || null,
          })
        } catch (error) {
          console.error('Registration failed:', error)
          throw error
        }
      },

      logout: async () => {
        try {
          await apiClient.post('/api/auth/logout')
        } catch (error) {
          console.error('Logout failed:', error)
        } finally {
          // Clear access token from localStorage
          localStorage.removeItem('access_token')
          
          set({
            user: null,
            isAuthenticated: false,
            csrfToken: null,
            accessToken: null,
          })
        }
      },

      setCsrfToken: (token: string) => {
        set({ csrfToken: token })
      },

      setAccessToken: (token: string) => {
        localStorage.setItem('access_token', token)
        set({ accessToken: token })
      },
      
      getAccessToken: () => {
        // First try to get from state
        const state = useAuthStore.getState() as AuthState
        if (state.accessToken) {
          return state.accessToken
        }
        
        // Fallback to localStorage
        return localStorage.getItem('access_token')
      },

      getCsrfToken: () => {
        // Get from state
        const state = useAuthStore.getState() as AuthState
        return state.csrfToken
      },

      checkAuth: async () => {
        try {
          const response = await apiClient.get('/api/auth/me')
          if (response.status === 200) {
            // If we can access the user endpoint, we're authenticated
            set({ 
              user: response.data,
              isAuthenticated: true,
              // Keep existing tokens
              accessToken: useAuthStore.getState().accessToken || null,
              csrfToken: useAuthStore.getState().csrfToken || null,
            })
            
            // Load user settings if authenticated
            try {
              const { useSettingsStore } = await import('./components/SettingsStore')
              const settingsStore = useSettingsStore.getState()
              await settingsStore.loadSettings()
            } catch (error) {
              console.error('Failed to load settings during auth check:', error)
            }
          }
        } catch (error) {
          // Clear access token from localStorage
          localStorage.removeItem('access_token')
          
          set({
            user: null,
            isAuthenticated: false,
            csrfToken: null,
            accessToken: null,
          })
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        csrfToken: state.csrfToken,
        accessToken: state.accessToken,
      }),
    }
  )
)

// Expose auth store globally for API client access
if (typeof window !== 'undefined') {
  (window as any).__AUTH_STORE__ = useAuthStore
}
