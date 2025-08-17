/**
 * Unified WebSocket Service
 * Centralizes all WebSocket connections to prevent duplicates and manage connections efficiently
 */
import React from 'react'
import { useAuthStore } from '../features/auth/store'

interface WebSocketMessage {
  type: string
  _msg_id?: string  // Message ID for deduplication
  [key: string]: any
}

interface ConnectionConfig {
  endpoint: string
  connectionType: 'research' | 'writing' | 'document'
  sessionId?: string
  onMessage?: (message: WebSocketMessage) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Error) => void
}

interface ManagedConnection {
  ws: WebSocket | null
  config: ConnectionConfig
  isConnecting: boolean
  isConnected: boolean
  reconnectAttempts: number
  reconnectTimer?: number
  pingInterval?: number
  lastPing: number
  messageQueue: WebSocketMessage[]
  messageCache: Set<string>  // For deduplication
  listeners: Map<string, Set<(data: any) => void>>
}

class UnifiedWebSocketService {
  private static instance: UnifiedWebSocketService
  private connections: Map<string, ManagedConnection> = new Map()
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private pingIntervalTime = 20000  // 20 seconds
  private messageCacheTTL = 1000  // 1 second for deduplication

  private constructor() {
    // Singleton pattern
    // console.log('UnifiedWebSocketService initialized')
  }

  static getInstance(): UnifiedWebSocketService {
    if (!UnifiedWebSocketService.instance) {
      UnifiedWebSocketService.instance = new UnifiedWebSocketService()
    }
    return UnifiedWebSocketService.instance
  }

  /**
   * Get or create a connection for the given configuration
   */
  async getConnection(config: ConnectionConfig): Promise<string> {
    const connectionKey = this.getConnectionKey(config)
    
    // Check if connection already exists
    let connection = this.connections.get(connectionKey)
    
    if (connection) {
      // Update the config callbacks even if connection exists
      // This ensures callbacks are always current
      if (config.onMessage) {
        connection.config.onMessage = config.onMessage
      }
      if (config.onConnect) {
        connection.config.onConnect = config.onConnect
      }
      if (config.onDisconnect) {
        connection.config.onDisconnect = config.onDisconnect
      }
      if (config.onError) {
        connection.config.onError = config.onError
      }
      
      // Connection exists, check if it's active
      if (connection.isConnected) {
        // console.log(`Reusing existing connection: ${connectionKey}`)
        return connectionKey
      }
      
      // Connection exists but not connected, reconnect
      if (!connection.isConnecting) {
        await this.connect(connectionKey)
      }
      return connectionKey
    }
    
    // Create new connection
    connection = this.createConnection(config)
    this.connections.set(connectionKey, connection)
    
    // Start connection
    await this.connect(connectionKey)
    return connectionKey
  }

  /**
   * Generate a unique key for the connection
   */
  private getConnectionKey(config: ConnectionConfig): string {
    if (config.connectionType === 'writing' && config.sessionId) {
      return `${config.connectionType}:${config.sessionId}`
    }
    return `${config.connectionType}:${config.endpoint}`
  }

  /**
   * Create a new managed connection
   */
  private createConnection(config: ConnectionConfig): ManagedConnection {
    return {
      ws: null,
      config,
      isConnecting: false,
      isConnected: false,
      reconnectAttempts: 0,
      lastPing: Date.now(),
      messageQueue: [],
      messageCache: new Set(),
      listeners: new Map()
    }
  }

  /**
   * Connect or reconnect a WebSocket
   */
  private async connect(connectionKey: string): Promise<void> {
    const connection = this.connections.get(connectionKey)
    if (!connection) {
      throw new Error(`Connection not found: ${connectionKey}`)
    }

    // Prevent multiple connection attempts
    if (connection.isConnecting || connection.isConnected) {
      return
    }

    connection.isConnecting = true

    try {
      // Close existing connection if any
      if (connection.ws) {
        connection.ws.close()
        connection.ws = null
      }

      // Get authentication token
      const token = this.getAuthToken()
      if (!token) {
        throw new Error('No authentication token available')
      }

      // Build WebSocket URL
      const wsUrl = this.buildWebSocketUrl(connection.config.endpoint, token)
      
      // console.log(`Connecting to WebSocket: ${connectionKey}`)
      const ws = new WebSocket(wsUrl)

      // Set up event handlers
      ws.onopen = () => {
        // console.log(`WebSocket connected: ${connectionKey}`)
        connection.isConnecting = false
        connection.isConnected = true
        connection.reconnectAttempts = 0
        
        // Start ping interval
        this.startPingInterval(connectionKey)
        
        // Send queued messages
        this.flushMessageQueue(connectionKey)
        
        // Call connection callback
        if (connection.config.onConnect) {
          connection.config.onConnect()
        }
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          
          // Check for duplicate messages
          if (message._msg_id && this.isDuplicateMessage(connection, message._msg_id)) {
            console.debug(`Duplicate message ignored: ${message._msg_id}`)
            return
          }
          
          // Handle different message types
          this.handleMessage(connectionKey, message)
          
          // Call message callback
          if (connection.config.onMessage) {
            connection.config.onMessage(message)
          }
        } catch (error) {
          console.error('Error processing WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.error(`WebSocket error for ${connectionKey}:`, error)
        if (connection.config.onError) {
          connection.config.onError(new Error('WebSocket error'))
        }
      }

      ws.onclose = (event) => {
        // console.log(`WebSocket closed for ${connectionKey}:`, event.code, event.reason)
        connection.isConnecting = false
        connection.isConnected = false
        connection.ws = null
        
        // Stop ping interval
        this.stopPingInterval(connectionKey)
        
        // Call disconnect callback
        if (connection.config.onDisconnect) {
          connection.config.onDisconnect()
        }
        
        // Attempt reconnection if not a clean close
        if (event.code !== 1000 && connection.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect(connectionKey)
        }
      }

      connection.ws = ws
    } catch (error) {
      console.error(`Failed to connect WebSocket ${connectionKey}:`, error)
      connection.isConnecting = false
      connection.isConnected = false
      
      if (connection.config.onError) {
        connection.config.onError(error as Error)
      }
      
      // Schedule reconnection
      if (connection.reconnectAttempts < this.maxReconnectAttempts) {
        this.scheduleReconnect(connectionKey)
      }
    }
  }

  /**
   * Schedule a reconnection attempt
   */
  private scheduleReconnect(connectionKey: string) {
    const connection = this.connections.get(connectionKey)
    if (!connection) return

    connection.reconnectAttempts++
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, connection.reconnectAttempts - 1),
      30000  // Max 30 seconds
    )

    // console.log(`Scheduling reconnect for ${connectionKey} in ${delay}ms (attempt ${connection.reconnectAttempts})`)

    connection.reconnectTimer = window.setTimeout(() => {
      this.connect(connectionKey)
    }, delay)
  }

  /**
   * Start ping interval to keep connection alive
   */
  private startPingInterval(connectionKey: string) {
    const connection = this.connections.get(connectionKey)
    if (!connection) return

    // Clear existing interval if any
    this.stopPingInterval(connectionKey)

    connection.pingInterval = window.setInterval(() => {
      if (connection.ws?.readyState === WebSocket.OPEN) {
        const pingMessage = {
          type: 'ping',
          timestamp: Date.now()
        }
        connection.ws.send(JSON.stringify(pingMessage))
        connection.lastPing = Date.now()
      }
    }, this.pingIntervalTime)
  }

  /**
   * Stop ping interval
   */
  private stopPingInterval(connectionKey: string) {
    const connection = this.connections.get(connectionKey)
    if (!connection || !connection.pingInterval) return

    clearInterval(connection.pingInterval)
    connection.pingInterval = undefined
  }

  /**
   * Check if a message is a duplicate
   */
  private isDuplicateMessage(connection: ManagedConnection, messageId: string): boolean {
    if (connection.messageCache.has(messageId)) {
      return true
    }

    // Add to cache
    connection.messageCache.add(messageId)

    // Clean old entries
    setTimeout(() => {
      connection.messageCache.delete(messageId)
    }, this.messageCacheTTL)

    return false
  }

  /**
   * Handle incoming messages
   */
  private handleMessage(connectionKey: string, message: WebSocketMessage) {
    const connection = this.connections.get(connectionKey)
    if (!connection) return

    // Handle system messages
    if (message.type === 'pong') {
      // Pong response, update last ping time
      connection.lastPing = Date.now()
      return
    }

    if (message.type === 'heartbeat') {
      // Respond with heartbeat acknowledgment
      this.send(connectionKey, {
        type: 'heartbeat_ack',
        timestamp: Date.now()
      })
      return
    }

    // Emit to listeners
    const listeners = connection.listeners.get(message.type)
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(message)
        } catch (error) {
          console.error(`Error in WebSocket listener for ${message.type}:`, error)
        }
      })
    }

    // Emit to 'all' listeners
    const allListeners = connection.listeners.get('all')
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

  /**
   * Send a message through the WebSocket
   */
  send(connectionKey: string, message: any) {
    const connection = this.connections.get(connectionKey)
    if (!connection) {
      console.warn(`Connection not found: ${connectionKey}`)
      return
    }

    if (connection.ws?.readyState === WebSocket.OPEN) {
      connection.ws.send(JSON.stringify(message))
    } else {
      // Queue message for later
      // console.log(`Queueing message for ${connectionKey} (not connected)`)
      connection.messageQueue.push(message)
    }
  }

  /**
   * Send all queued messages
   */
  private flushMessageQueue(connectionKey: string) {
    const connection = this.connections.get(connectionKey)
    if (!connection || !connection.ws || connection.ws.readyState !== WebSocket.OPEN) {
      return
    }

    while (connection.messageQueue.length > 0) {
      const message = connection.messageQueue.shift()
      if (message) {
        connection.ws.send(JSON.stringify(message))
      }
    }
  }

  /**
   * Subscribe to a specific message type
   */
  subscribe(connectionKey: string, eventType: string, callback: (data: any) => void) {
    const connection = this.connections.get(connectionKey)
    if (!connection) {
      console.warn(`Connection not found: ${connectionKey}`)
      return () => {}
    }

    if (!connection.listeners.has(eventType)) {
      connection.listeners.set(eventType, new Set())
    }
    connection.listeners.get(eventType)!.add(callback)

    // Return unsubscribe function
    return () => {
      const listeners = connection.listeners.get(eventType)
      if (listeners) {
        listeners.delete(callback)
        if (listeners.size === 0) {
          connection.listeners.delete(eventType)
        }
      }
    }
  }

  /**
   * Close a connection
   */
  disconnect(connectionKey: string) {
    const connection = this.connections.get(connectionKey)
    if (!connection) return

    // Clear reconnect timer
    if (connection.reconnectTimer) {
      clearTimeout(connection.reconnectTimer)
    }

    // Stop ping interval
    this.stopPingInterval(connectionKey)

    // Close WebSocket
    if (connection.ws) {
      connection.ws.close(1000, 'Client disconnect')
      connection.ws = null
    }

    // Remove connection
    this.connections.delete(connectionKey)
    // console.log(`Disconnected: ${connectionKey}`)
  }

  /**
   * Check if a connection is active
   */
  isConnected(connectionKey: string): boolean {
    const connection = this.connections.get(connectionKey)
    return connection?.isConnected || false
  }

  /**
   * Get connection statistics
   */
  getStats() {
    const stats: any = {
      totalConnections: this.connections.size,
      connections: {}
    }

    this.connections.forEach((conn, key) => {
      stats.connections[key] = {
        isConnected: conn.isConnected,
        isConnecting: conn.isConnecting,
        reconnectAttempts: conn.reconnectAttempts,
        queuedMessages: conn.messageQueue.length,
        cachedMessages: conn.messageCache.size,
        listeners: conn.listeners.size
      }
    })

    return stats
  }

  /**
   * Build WebSocket URL with authentication
   */
  private buildWebSocketUrl(endpoint: string, token: string): string {
    let wsBaseUrl = import.meta.env.VITE_API_WS_URL
    if (!wsBaseUrl) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      wsBaseUrl = `${protocol}//${window.location.host}`
    }
    return `${wsBaseUrl}${endpoint}?token=${encodeURIComponent(token)}`
  }

  /**
   * Get authentication token
   */
  private getAuthToken(): string | null {
    // Try auth store first
    const authToken = useAuthStore.getState().getAccessToken()
    if (authToken) return authToken

    // Try cookies
    const cookies = document.cookie.split(';')
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=')
      if (name === 'access_token') {
        return decodeURIComponent(value)
      }
    }

    // Try localStorage
    const localToken = localStorage.getItem('access_token')
    if (localToken) return localToken

    return null
  }
}

// Export singleton instance
export const unifiedWebSocketService = UnifiedWebSocketService.getInstance()

// Export convenience hook for React components
export function useUnifiedWebSocket(config: ConnectionConfig) {
  const [connectionKey, setConnectionKey] = React.useState<string | null>(null)
  const [isConnected, setIsConnected] = React.useState(false)
  const [error, setError] = React.useState<Error | null>(null)

  React.useEffect(() => {
    let mounted = true

    const connect = async () => {
      try {
        const key = await unifiedWebSocketService.getConnection({
          ...config,
          onConnect: () => {
            if (mounted) {
              setIsConnected(true)
              setError(null)
            }
            config.onConnect?.()
          },
          onDisconnect: () => {
            if (mounted) {
              setIsConnected(false)
            }
            config.onDisconnect?.()
          },
          onError: (err) => {
            if (mounted) {
              setError(err)
            }
            config.onError?.(err)
          }
        })
        
        if (mounted) {
          setConnectionKey(key)
        }
      } catch (err) {
        if (mounted) {
          setError(err as Error)
        }
      }
    }

    connect()

    return () => {
      mounted = false
      // Don't disconnect on unmount - let the service manage connections
    }
  }, [config.endpoint, config.connectionType, config.sessionId])

  const send = React.useCallback((message: any) => {
    if (connectionKey) {
      unifiedWebSocketService.send(connectionKey, message)
    }
  }, [connectionKey])

  const subscribe = React.useCallback((eventType: string, callback: (data: any) => void) => {
    if (connectionKey) {
      return unifiedWebSocketService.subscribe(connectionKey, eventType, callback)
    }
    return () => {}
  }, [connectionKey])

  return {
    isConnected,
    error,
    send,
    subscribe,
    connectionKey
  }
}

export default unifiedWebSocketService