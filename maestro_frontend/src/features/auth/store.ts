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
  accessToken: string | null
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  setCsrfToken: (token: string) => void
  setAccessToken: (token: string) => void
  getAccessToken: () => string | null
  getCsrfToken: () => string | null
  checkAuth: () => Promise<void>
}

// @ts-ignore - Zustand v4/v5 TypeScript compatibility issues
export const useAuthStore = create<AuthState>()(
  // @ts-ignore
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      csrfToken: null,
      accessToken: null,

      login: async (username: string, password: string, rememberMe?: boolean) => {
        try {
          const formData = new FormData()
          formData.append('username', username)
          formData.append('password', password)
          
          const headers: Record<string, string> = {
            'Content-Type': 'application/x-www-form-urlencoded',
          }
          
          if (rememberMe) {
            headers['X-Remember-Me'] = 'true'
          }

          const response = await apiClient.post('/api/auth/login', 
            new URLSearchParams(formData as any), 
            { headers }
          )
          
          if (response.data.access_token) {
            set({ 
              user: response.data.user,
              isAuthenticated: true,
              accessToken: response.data.access_token
            })
            
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${response.data.access_token}`
          }
        } catch (error) {
          console.error('Login failed:', error)
          throw error
        }
      },

      register: async (username: string, password: string) => {
        try {
          const response = await apiClient.post('/api/auth/register', {
            username,
            password
          })
          
          if (response.data.access_token) {
            set({ 
              user: response.data.user,
              isAuthenticated: true,
              accessToken: response.data.access_token
            })
            
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${response.data.access_token}`
          }
        } catch (error) {
          console.error('Registration failed:', error)
          throw error
        }
      },

      logout: async () => {
        try {
          await apiClient.post('/api/auth/logout')
        } catch (error) {
          console.error('Logout request failed:', error)
        } finally {
          set({ 
            user: null, 
            isAuthenticated: false,
            accessToken: null
          })
          
          delete apiClient.defaults.headers.common['Authorization']
        }
      },

      setCsrfToken: (token: string) => {
        set({ csrfToken: token })
        apiClient.defaults.headers.common['X-CSRF-Token'] = token
      },
      
      setAccessToken: (token: string) => {
        set({ accessToken: token })
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`
      },
      
      getAccessToken: () => {
        return (get() as AuthState).accessToken
      },
      
      getCsrfToken: () => {
        return (get() as AuthState).csrfToken
      },

      checkAuth: async () => {
        try {
          const token = (get() as AuthState).accessToken
          if (!token) {
            set({ 
              user: null, 
              isAuthenticated: false 
            })
            return
          }

          const response = await apiClient.get('/api/auth/me', {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })
          
          if (response.data) {
            set({ 
              user: response.data,
              isAuthenticated: true 
            })
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`
          } else {
            set({ 
              user: null, 
              isAuthenticated: false,
              accessToken: null
            })
            delete apiClient.defaults.headers.common['Authorization']
          }
        } catch (error) {
          console.error('Auth check failed:', error)
          set({ 
            user: null, 
            isAuthenticated: false,
            accessToken: null
          })
          delete apiClient.defaults.headers.common['Authorization']
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state: AuthState) => ({
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