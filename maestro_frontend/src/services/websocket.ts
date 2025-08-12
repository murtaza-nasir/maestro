/**
 * WebSocket service for real-time mission updates
 */
import React from 'react'
import { useAuthStore } from '../features/auth/store'

interface WebSocketMessage {
  type: string
  [key: string]: any
}

class MissionWebSocketService {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private listeners: Map<string, Set<(data: any) => void>> = new Map()
  private missionId: string | null = null
  private isConnecting = false
  private connectionPromise: Promise<void> | null = null
  // private messageQueue: any[] = []

  connect(missionId: string): Promise<void> {
    // Connection pooling: reuse existing connection if same mission
    if (this.ws?.readyState === WebSocket.OPEN && this.missionId === missionId) {
      return Promise.resolve()
    }

    // Connection deduplication: return existing promise if already connecting to same mission
    if (this.isConnecting && this.missionId === missionId && this.connectionPromise) {
      return this.connectionPromise
    }

    // Create new connection promise
    this.connectionPromise = new Promise((resolve, reject) => {
      this.disconnect()
      this.missionId = missionId
      this.isConnecting = true

      // Get WebSocket URL using nginx proxy (same origin)
      let wsBaseUrl = import.meta.env.VITE_API_WS_URL;
      if (!wsBaseUrl) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsBaseUrl = `${protocol}//${window.location.host}`;
      }
      
      // Only log in development mode
      if (import.meta.env.DEV) {
        console.log(`Using WebSocket base URL: ${wsBaseUrl}`)
      }
      
      // Get JWT token from cookies for authentication
      const token = this.getTokenFromCookie()
      
      if (!token && import.meta.env.DEV) {
        console.warn('No authentication token found for WebSocket connection')
      }
      
      // Always include token in URL to avoid relying on cookies being sent
      const wsUrl = `${wsBaseUrl}/api/ws/missions/${missionId}?token=${encodeURIComponent(token || '')}`
      
      if (import.meta.env.DEV) {
        console.log(`Attempting WebSocket connection to: ${wsUrl}`)
      }

      try {
        this.ws = new WebSocket(wsUrl)

        this.ws.onopen = () => {
          if (import.meta.env.DEV) {
            console.log(`Connected to mission WebSocket: ${missionId}`)
          }
          this.reconnectAttempts = 0
          this.isConnecting = false
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            this.handleMessage(message)
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        this.ws.onclose = (event) => {
          if (import.meta.env.DEV) {
            console.log('Mission WebSocket closed:', event.code, event.reason)
          }
          this.isConnecting = false
          this.ws = null
          
          if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect()
          }
        }

        this.ws.onerror = (error) => {
          console.error('Mission WebSocket error:', error)
          this.isConnecting = false
          reject(error)
        }

        // Connection timeout
        setTimeout(() => {
          if (this.isConnecting) {
            this.isConnecting = false
            reject(new Error('Connection timeout'))
          }
        }, 10000)

      } catch (error) {
        this.isConnecting = false
        this.connectionPromise = null
        reject(error)
      }
    })

    return this.connectionPromise
  }

  disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }
    this.missionId = null
    this.isConnecting = false
    this.connectionPromise = null
    // this.messageQueue = []
  }

  private scheduleReconnect() {
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    console.log(`Scheduling WebSocket reconnect attempt ${this.reconnectAttempts} in ${delay}ms`)
    
    setTimeout(() => {
      if (this.missionId && this.reconnectAttempts <= this.maxReconnectAttempts) {
        this.connect(this.missionId).catch(console.error)
      }
    }, delay)
  }

  private handleMessage(message: WebSocketMessage) {
    const { type } = message

    // Emit to specific listeners
    const typeListeners = this.listeners.get(type)
    if (typeListeners) {
      typeListeners.forEach(listener => {
        try {
          listener(message)
        } catch (error) {
          console.error(`Error in WebSocket listener for ${type}:`, error)
        }
      })
    }

    // Emit to 'all' listeners
    const allListeners = this.listeners.get('all')
    if (allListeners) {
      allListeners.forEach(listener => {
        try {
          listener(message)
        } catch (error) {
          console.error('Error in WebSocket all listener:', error)
        }
      })
    }
  }

  subscribe(eventType: string, callback: (data: any) => void) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set())
    }
    this.listeners.get(eventType)!.add(callback)

    // Return unsubscribe function
    return () => {
      const listeners = this.listeners.get(eventType)
      if (listeners) {
        listeners.delete(callback)
        if (listeners.size === 0) {
          this.listeners.delete(eventType)
        }
      }
    }
  }

  unsubscribe(eventType: string, callback: (data: any) => void) {
    const listeners = this.listeners.get(eventType)
    if (listeners) {
      listeners.delete(callback)
      if (listeners.size === 0) {
        this.listeners.delete(eventType)
      }
    }
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket not connected, cannot send message:', message)
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  // Utility method to send ping
  ping() {
    this.send({
      type: 'ping',
      timestamp: new Date().toISOString()
    })
  }


  // Helper method to get JWT token from auth store or cookies
  private getTokenFromCookie(): string | null {
    // First try to get token from auth store
    const authToken = useAuthStore.getState().getAccessToken()
    if (authToken) {
      return authToken
    }
    
    // Check cookies for token
    const cookies = document.cookie.split(';')
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=')
      if (name === 'access_token') {
        return decodeURIComponent(value)
      }
    }
    
    // Try to get token from localStorage as fallback
    const localToken = localStorage.getItem('access_token')
    if (localToken) {
      return localToken
    }
    
    // Only warn in development mode
    if (import.meta.env.DEV) {
      console.warn('No authentication token found for WebSocket connection')
    }
    return null
  }
}

// Create singleton instance
export const missionWebSocket = new MissionWebSocketService()

// React hook for using WebSocket in components
export function useMissionWebSocket(missionId: string | null) {
  const [isConnected, setIsConnected] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!missionId) {
      setIsConnected(false)
      setError(null)
      return
    }

    let mounted = true

    const connect = async () => {
      try {
        await missionWebSocket.connect(missionId)
        if (mounted) {
          setIsConnected(true)
          setError(null)
        }
      } catch (err) {
        if (mounted) {
          setIsConnected(false)
          setError(err instanceof Error ? err.message : 'Connection failed')
        }
      }
    }

    connect()

    // Set up connection status monitoring
    const checkConnection = () => {
      if (mounted) {
        setIsConnected(missionWebSocket.isConnected())
      }
    }

    const interval = setInterval(checkConnection, 1000)

    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [missionId])

  const subscribe = React.useCallback((eventType: string, callback: (data: any) => void) => {
    return missionWebSocket.subscribe(eventType, callback)
  }, [])

  const send = React.useCallback((message: any) => {
    missionWebSocket.send(message)
  }, [])

  return {
    isConnected,
    error,
    subscribe,
    send
  }
}

export default missionWebSocket
