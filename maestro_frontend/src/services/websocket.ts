/**
 * Research WebSocket service - now uses UnifiedWebSocketService
 * Maintains backward compatibility while delegating to unified service
 */
import React from 'react'
import { unifiedWebSocketService, useUnifiedWebSocket } from './unifiedWebSocketService'
import { useMissionStore, type Log } from '../features/mission/store'
import { ensureDate } from '../utils/timezone'

interface WebSocketMessage {
  type: string
  mission_id?: string
  [key: string]: any
}

class ResearchWebSocketService {
  private subscribedMissions: Set<string> = new Set()
  private connectionKey: string | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()
  private missionHandlers: Map<string, () => void> = new Map() // Store cleanup functions for mission handlers

  async connect(): Promise<void> {
    // console.log('ResearchWebSocketService.connect() called, existing key:', this.connectionKey)
    
    // Always update the connection to ensure message handler is current
    this.connectionKey = await unifiedWebSocketService.getConnection({
      endpoint: '/api/ws/research',
      connectionType: 'research',
      onMessage: (message) => {
        // console.log('ResearchWebSocketService received message:', message.type, message.mission_id)
        this.handleMessage(message)
      }
    })
    // console.log('ResearchWebSocketService connected with key:', this.connectionKey)
    
    // Resubscribe to all missions after connection
    if (this.subscribedMissions.size > 0) {
      // console.log('Resubscribing to missions:', Array.from(this.subscribedMissions))
      this.subscribedMissions.forEach(missionId => {
        this.send({
          type: 'subscribe',
          mission_id: missionId
        })
      })
    }
  }

  disconnect() {
    // Mark as intentional disconnect
    this.subscribedMissions.clear()
    this.listeners.clear()
    // Don't actually disconnect - let unified service manage
  }

  subscribeMission(missionId: string) {
    if (this.subscribedMissions.has(missionId)) {
      if (import.meta.env.DEV) {
        // console.log(`Already subscribed to mission ${missionId}`)
      }
      return
    }
    
    this.subscribedMissions.add(missionId)
    
    // Set up persistent handlers for this mission at the service level
    this.setupMissionHandlers(missionId)
    
    // Send subscription message through unified service
    this.send({
      type: 'subscribe',
      mission_id: missionId
    })
    // console.log(`Subscribed to mission ${missionId}`)
  }

  unsubscribeMission(missionId: string) {
    if (!this.subscribedMissions.has(missionId)) {
      return
    }
    
    this.subscribedMissions.delete(missionId)
    
    // Clean up mission handlers
    const cleanup = this.missionHandlers.get(missionId)
    if (cleanup) {
      cleanup()
      this.missionHandlers.delete(missionId)
    }
    
    this.send({
      type: 'unsubscribe',
      mission_id: missionId
    })
    // console.log(`Unsubscribed from mission ${missionId}`)
  }

  private setupMissionHandlers(missionId: string) {
    // Clean up any existing handlers for this mission
    const existingCleanup = this.missionHandlers.get(missionId)
    if (existingCleanup) {
      existingCleanup()
    }

    const cleanupFunctions: (() => void)[] = []
    
    // Create a deduplication cache that persists across handler calls
    // This prevents race conditions when multiple messages arrive simultaneously
    const logKeyCache = new Set<string>()
    let cacheInitialized = false
    
    // Create a processing queue to ensure sequential processing of log updates
    let processingQueue = Promise.resolve()

    // Helper function to create a unique key for a log entry
    const getLogKey = (log: any) => {
      // Use log_id if available (backend v2), otherwise fall back to composite key
      if (log.log_id) {
        return log.log_id
      }
      // Fallback for older logs without log_id
      // Create a composite key from available fields
      const timestamp = log.timestamp instanceof Date ? log.timestamp.toISOString() : String(log.timestamp)
      const inputKey = log.input_summary ? `_${log.input_summary.substring(0, 100)}` : ''
      const outputKey = log.output_summary ? `_${log.output_summary.substring(0, 50)}` : ''
      const statusKey = log.status || 'unknown'
      // Include more fields to ensure uniqueness
      const key = `${timestamp}_${log.agent_name}_${log.action}${inputKey}${outputKey}_${statusKey}`
      
      // Debug logging for problematic messages
      if (log.action && (log.action.includes('Rerank') || log.action.includes('Assigned'))) {
        // console.log(`Key for ${log.action}: ${key}`, { log_id: log.log_id, timestamp, action: log.action })
      }
      
      return key
    }

    // Handler for logs updates
    const logsHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      
      // Queue the log processing to ensure sequential execution
      processingQueue = processingQueue.then(() => {
        const newLogs: Log[] = message.data.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))

        const currentState = useMissionStore.getState()
        const existingLogs = currentState.missionLogs[missionId] || []
        
        let updatedLogs: Log[]
        if (message.action === 'replace') {
          // Clear cache on replace
          logKeyCache.clear()
          cacheInitialized = true
          newLogs.forEach(log => logKeyCache.add(getLogKey(log)))
          updatedLogs = newLogs
        } else {
          // Initialize cache from existing logs only once per mission subscription
          if (!cacheInitialized && existingLogs.length > 0) {
            existingLogs.forEach(log => logKeyCache.add(getLogKey(log)))
            cacheInitialized = true
            // console.log(`Initialized cache with ${existingLogs.length} existing logs for mission ${missionId}`)
          }
          
          // Filter out duplicates using the persistent cache
          const uniqueNewLogs = newLogs.filter(log => {
            const key = getLogKey(log)
            if (logKeyCache.has(key)) {
              // console.log(`Duplicate log detected and filtered: ${log.action}`, { key, log_id: log.log_id })
              return false
            }
            // Add to cache immediately to prevent duplicates from same batch
            logKeyCache.add(key)
            return true
          })
          
          updatedLogs = [...existingLogs, ...uniqueNewLogs].sort(
            (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
          )
          if (uniqueNewLogs.length > 0) {
            // console.log(`Appended ${uniqueNewLogs.length} new logs for mission ${missionId}`)
          }
        }
        
        currentState.setMissionLogs(missionId, updatedLogs)
      }).catch(error => {
        console.error('Error processing logs update:', error)
      })
    }

    // Handler for status updates
    const statusHandler = async (message: any) => {
      if (message.mission_id !== missionId) return
      // Backend sends status directly in message.status, not message.data.status
      if (message.status) {
        const { updateMissionStatus, setActiveTab } = useMissionStore.getState()
        updateMissionStatus(missionId, message.status)
        console.log(`Updated mission ${missionId} status to: ${message.status}`)
        
        // When mission completes, switch to draft tab and add a completion message
        if (message.status === 'completed') {
          setActiveTab('draft')
          console.log('Mission completed - switching to draft tab')
          
          // Add completion message to the chat
          try {
            // Import chat store dynamically to avoid circular dependencies
            const { useChatStore } = await import('../features/chat/store')
            const chatStore = useChatStore.getState()
            
            // Find the chat associated with this mission
            const chat = chatStore.chats.find(c => c.missionId === missionId)
            if (chat) {
              const completionMessage = `✅ **Research mission completed!**\n\nYour research report has been generated and is available in the Draft tab. You can:\n- Review and edit the report\n- Download it as Markdown or Word document\n- Use "Restart and Revise" to refine the research with additional feedback`
              
              await chatStore.addMessage(chat.id, {
                content: completionMessage,
                role: 'assistant'
              })
            }
          } catch (error) {
            console.error('Failed to add completion message to chat:', error)
          }
        }
      }
    }

    // Handler for plan updates
    const planHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data) {
        const { setMissionPlan } = useMissionStore.getState()
        setMissionPlan(missionId, message.data)
      }
    }

    // Handler for notes updates
    const notesHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data) {
        const { setMissionNotes, appendMissionNotes } = useMissionStore.getState()
        if (message.action === 'replace') {
          setMissionNotes(missionId, message.data)
        } else {
          appendMissionNotes(missionId, message.data)
        }
      }
    }

    // Handler for draft updates
    const draftHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data) {
        const { setMissionDraft } = useMissionStore.getState()
        setMissionDraft(missionId, message.data)
      }
    }

    // Handler for scratchpad updates
    const scratchpadHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data !== undefined) {
        const { updateMissionContext } = useMissionStore.getState()
        updateMissionContext(missionId, {
          agent_scratchpad: message.data
        })
      }
    }

    // Handler for thought pad updates
    const thoughtPadHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data) {
        const { updateMissionContext } = useMissionStore.getState()
        updateMissionContext(missionId, {
          thought_pad: message.data
        })
      }
    }

    // Handler for goal pad updates
    const goalPadHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.data) {
        const { updateMissionContext } = useMissionStore.getState()
        updateMissionContext(missionId, {
          goal_pad: message.data
        })
      }
    }

    // Handler for truncate data (when resuming from a specific round)
    const truncateHandler = (message: any) => {
      if (message.mission_id !== missionId) return
      if (message.type === 'truncate_data' && message.round_num) {
        console.log(`Truncating data for mission ${missionId} after round ${message.round_num - 1}`)
        const { setMissionLogs, setMissionNotes } = useMissionStore.getState()
        
        // Clear the log deduplication cache
        logKeyCache.clear()
        cacheInitialized = false
        
        // Clear logs and notes in the store
        // The backend will handle the actual truncation, we just clear the frontend state
        // and let the backend send us the correct data
        setMissionLogs(missionId, [])
        setMissionNotes(missionId, [])
        
        // Fetch fresh data from backend
        const { fetchMissionLogs, fetchMissionNotes } = useMissionStore.getState()
        setTimeout(() => {
          fetchMissionLogs(missionId)
          fetchMissionNotes(missionId)
        }, 1000) // Small delay to let backend complete truncation
      }
    }

    // Subscribe all handlers
    cleanupFunctions.push(this.subscribe('logs_update', logsHandler))
    cleanupFunctions.push(this.subscribe('status_update', statusHandler))
    cleanupFunctions.push(this.subscribe('plan_update', planHandler))
    cleanupFunctions.push(this.subscribe('notes_update', notesHandler))
    cleanupFunctions.push(this.subscribe('draft_update', draftHandler))
    cleanupFunctions.push(this.subscribe('scratchpad_update', scratchpadHandler))
    cleanupFunctions.push(this.subscribe('thought_pad_update', thoughtPadHandler))
    cleanupFunctions.push(this.subscribe('goal_pad_update', goalPadHandler))
    cleanupFunctions.push(this.subscribe('mission_update', truncateHandler))

    // Store combined cleanup function
    this.missionHandlers.set(missionId, () => {
      cleanupFunctions.forEach(cleanup => cleanup())
      // Clear the deduplication cache
      logKeyCache.clear()
      cacheInitialized = false
    })

    // console.log(`Set up persistent handlers for mission ${missionId}`)
  }

  private handleMessage(message: WebSocketMessage) {
    const { type, mission_id } = message
    // console.log(`ResearchWebSocketService.handleMessage: type=${type}, mission_id=${mission_id}, subscribedMissions=${Array.from(this.subscribedMissions)}, listenersCount=${this.listeners.size}`)

    // Handle system messages
    if (type === 'heartbeat') {
      this.send({
        type: 'heartbeat_ack',
        timestamp: new Date().toISOString()
      })
      if (import.meta.env.DEV) {
        // console.log('Heartbeat received and acknowledged')
      }
      return
    }

    if (type === 'pong') {
      if (import.meta.env.DEV) {
        // console.log('Pong received')
      }
      return
    }

    // Check if this is a mission-specific message
    if (mission_id) {
      // Only process if we're subscribed to this mission
      if (!this.subscribedMissions.has(mission_id)) {
        console.warn(`Ignoring message for unsubscribed mission ${mission_id}. Subscribed missions:`, Array.from(this.subscribedMissions))
        return
      }
    }

    // Emit to specific listeners
    const typeListeners = this.listeners.get(type)
    // console.log(`Listeners for type '${type}':`, typeListeners ? typeListeners.size : 0)
    if (typeListeners && typeListeners.size > 0) {
      // console.log(`Emitting to ${typeListeners.size} listeners for type '${type}'`)
      typeListeners.forEach(listener => {
        try {
          listener(message)
          // console.log(`Successfully called listener for ${type}`)
        } catch (error) {
          console.error(`Error in WebSocket listener for ${type}:`, error)
        }
      })
    } else {
      console.warn(`No listeners registered for message type: ${type}. Available types:`, Array.from(this.listeners.keys()))
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
    if (this.connectionKey) {
      unifiedWebSocketService.send(this.connectionKey, message)
    } else {
      console.warn('Research WebSocket not connected, cannot send message:', message)
    }
  }

  isConnected(): boolean {
    return this.connectionKey ? unifiedWebSocketService.isConnected(this.connectionKey) : false
  }

  ping() {
    this.send({
      type: 'ping',
      timestamp: new Date().toISOString()
    })
  }
}

// Create singleton instance
export const researchWebSocket = new ResearchWebSocketService()

// React hook for using the research WebSocket
export function useResearchWebSocket() {
  const [isConnected, setIsConnected] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // Use unified WebSocket with research configuration
  const unified = useUnifiedWebSocket({
    endpoint: '/api/ws/research',
    connectionType: 'research',
    onConnect: () => {
      setIsConnected(true)
      setError(null)
      // Re-establish research WebSocket connection to re-subscribe to missions
      researchWebSocket.connect().catch(console.error)
    },
    onDisconnect: () => {
      setIsConnected(false)
    },
    onError: (err) => {
      setError(err.message)
    }
  })

  React.useEffect(() => {
    // Ensure research service is connected
    // console.log('useResearchWebSocket: Ensuring connection')
    researchWebSocket.connect().catch(console.error)
    
    // Cleanup on unmount
    return () => {
      // console.log('useResearchWebSocket: Component unmounting')
    }
  }, [])

  const subscribeMission = React.useCallback((missionId: string) => {
    researchWebSocket.subscribeMission(missionId)
  }, [])

  const unsubscribeMission = React.useCallback((missionId: string) => {
    researchWebSocket.unsubscribeMission(missionId)
  }, [])

  const subscribe = React.useCallback((eventType: string, callback: (data: any) => void) => {
    return researchWebSocket.subscribe(eventType, callback)
  }, [])

  const send = React.useCallback((message: any) => {
    researchWebSocket.send(message)
  }, [])

  return {
    isConnected: unified.isConnected,
    error: unified.error?.message || null,
    subscribe,
    send,
    subscribeMission,
    unsubscribeMission
  }
}

export default researchWebSocket