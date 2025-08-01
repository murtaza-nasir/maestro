import axios from 'axios'

// API configuration
export const API_CONFIG = {
  // Use environment variable or default to localhost for development
  BASE_URL: import.meta.env.VITE_API_HTTP_URL || 'http://localhost:8001',
  WS_URL: import.meta.env.VITE_API_WS_URL || 'ws://localhost:8001',
  
  // API endpoints
  ENDPOINTS: {
    AUTH: {
      LOGIN: '/api/auth/login',
      REGISTER: '/api/auth/register',
      LOGOUT: '/api/auth/logout',
      ME: '/api/auth/me',
    },
    CHAT: {
      SEND: '/api/chat',
      STATUS: '/api/chat/status',
    },
    CHATS: {
      CREATE: '/api/chats',
      LIST: '/api/chats',
      GET: '/api/chats/:id',
      UPDATE: '/api/chats/:id',
      DELETE: '/api/chats/:id',
    },
    MISSIONS: {
      CREATE: '/api/missions',
      STATUS: (id: string) => `/api/missions/${id}/status`,
      STATS: (id: string) => `/api/missions/${id}/stats`,
      PLAN: (id: string) => `/api/missions/${id}/plan`,
      REPORT: (id: string) => `/api/missions/${id}/report`,
      START: (id: string) => `/api/missions/${id}/start`,
      LOGS: (id: string) => `/api/missions/${id}/logs`,
      NOTES: (id: string) => `/api/missions/${id}/notes`,
      DRAFT: (id: string) => `/api/missions/${id}/draft`,
    },
    DOCUMENTS: {
      GROUPS: '/api/document-groups/',
      UPLOAD: '/api/documents/upload',
    },
    SYSTEM: {
      STATUS: '/api/system/status',
    },
    SETTINGS: {
      GET: '/api/me/settings',
      UPDATE: '/api/me/settings',
      TEST_CONNECTION: '/api/me/settings/test-connection',
      GET_MODELS: '/api/me/settings/models',
    },
    PROFILE: {
      GET: '/api/me/profile',
      UPDATE: '/api/me/profile',
    },
  },
}

// Helper function to get token from multiple sources
const getAuthToken = (): string | null => {
  // Try localStorage first
  let token = localStorage.getItem('access_token')
  
  // Fallback to auth store if available
  if (!token) {
    try {
      // Try to get from auth store if it's available
      const authStore = (window as any).__AUTH_STORE__
      if (authStore && authStore.getState) {
        token = authStore.getState().accessToken
      }
    } catch (e) {
      // Ignore errors accessing auth store
    }
  }
  
  // Fallback to cookies
  if (!token) {
    const cookies = document.cookie.split(';')
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=')
      if (name === 'access_token') {
        token = value
        break
      }
    }
  }
  
  return token
}

// Helper function to get CSRF token from cookies
const getCsrfToken = (): string | null => {
  // First, try to get from auth store
  try {
    const authStore = (window as any).__AUTH_STORE__
    if (authStore && authStore.getState) {
      const state = authStore.getState()
      const token = state.csrfToken
      if (token) {
        // console.log('Found CSRF token in auth store:', token.substring(0, 10) + '...')
        return token
      }
    }
  } catch (e) {
    console.warn('Error accessing auth store for CSRF token:', e)
  }

  // Fallback to reading from cookie
  const cookies = document.cookie.split(';')
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=')
    if (name === 'csrf_token') {
      // console.log('Found CSRF token in cookie:', value.substring(0, 10) + '...')
      return value
    }
  }
  
  console.warn('No CSRF token found in auth store or cookies')
  return null
}

// Create axios instance with automatic token handling
export const apiClient = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  withCredentials: true, // Include cookies in requests
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add Authorization and CSRF headers
apiClient.interceptors.request.use(
  (config) => {
    // Add Authorization header
    const token = getAuthToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
      // console.log(`Adding Authorization header to ${config.method?.toUpperCase()} ${config.url}`)
    } else {
      console.log(`No token found for ${config.method?.toUpperCase()} ${config.url}`)
    }

    // Add CSRF token for state-changing methods
    if (config.method && ['post', 'put', 'delete', 'patch'].includes(config.method.toLowerCase())) {
      const csrfToken = getCsrfToken()
      if (csrfToken) {
        config.headers['x-csrf-token'] = csrfToken
        // console.log(`Adding CSRF token to ${config.method.toUpperCase()} ${config.url}:`, csrfToken.substring(0, 10) + '...')
      } else {
        console.warn(`CSRF token not found for ${config.method.toUpperCase()} ${config.url}`)
        console.warn('Available cookies:', document.cookie)
      }
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle authentication errors
apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      console.log('Authentication error detected, clearing stored tokens')
      // Clear stored tokens on 401 errors
      localStorage.removeItem('access_token')
      
      // Clear auth store if available
      try {
        const authStore = (window as any).__AUTH_STORE__
        if (authStore && authStore.getState && authStore.getState().logout) {
          authStore.getState().logout()
        }
      } catch (e) {
        // Ignore errors accessing auth store
      }
      
      // Redirect to login if not already there
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// Helper function to build full API URLs
export const buildApiUrl = (endpoint: string): string => {
  return `${API_CONFIG.BASE_URL}${endpoint}`
}

// Export default axios instance for backward compatibility
export default apiClient
