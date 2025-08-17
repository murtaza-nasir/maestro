/**
 * Writing WebSocket Service - now uses UnifiedWebSocketService
 * Maintains backward compatibility while preventing duplicate connections
 */
import { unifiedWebSocketService } from '../../../services/unifiedWebSocketService'

export interface WritingUpdate {
  type: 'agent_status' | 'draft_content_update' | 'connection_established' | 'pong' | 'chat_title_update' | 'stats_update' | 'heartbeat' | 'connection_lost' | string; // Allow any string for compatibility
  session_id?: string;
  status?: string;
  details?: string;
  action?: string;
  data?: any;
  timestamp?: number;
  chat_id?: string;
  title?: string;
}

interface StatusCallback {
  callback: (update: WritingUpdate) => void;
}

export class WritingWebSocketService {
  private statusCallbacks: Set<StatusCallback> = new Set();
  private currentSessionId: string | null = null;
  private connectionKey: string | null = null;
  private messageQueue: WritingUpdate[] = [];

  constructor() {
    // Don't auto-connect on construction
  }

  public async connectToSession(sessionId: string) {
    // Don't reconnect if already connected to the same session
    if (this.currentSessionId === sessionId && this.connectionKey && unifiedWebSocketService.isConnected(this.connectionKey)) {
      // console.log(`Already connected to writing session: ${sessionId}`);
      return;
    }

    // Disconnect from previous session if any
    if (this.currentSessionId && this.currentSessionId !== sessionId) {
      this.disconnect();
    }

    this.currentSessionId = sessionId;

    try {
      // Use unified service for connection - it will handle deduplication
      this.connectionKey = await unifiedWebSocketService.getConnection({
        endpoint: `/ws/${sessionId}`,
        connectionType: 'writing',
        sessionId: sessionId,
        onMessage: (message) => this.handleWebSocketMessage(message),
        onConnect: () => {
          // console.log(`Writing WebSocket connected for session: ${sessionId}`);
          // Process any queued messages
          this.processMessageQueue();
        },
        onDisconnect: () => {
          // console.log(`Writing WebSocket disconnected for session: ${sessionId}`);
          // Notify callbacks about disconnection
          this.notifyStatusCallbacks({
            type: 'connection_lost',
            session_id: sessionId
          });
        },
        onError: (error) => {
          console.error(`Writing WebSocket error for session ${sessionId}:`, error);
        }
      });
    } catch (error) {
      console.error('Failed to connect writing WebSocket:', error);
    }
  }

  public disconnect() {
    if (this.connectionKey) {
      // Don't actually disconnect - let unified service manage connections
      // Just clear our local state
      this.currentSessionId = null;
      this.connectionKey = null;
      this.messageQueue = [];
    }
  }

  public sendMessage(message: WritingUpdate) {
    if (this.connectionKey && unifiedWebSocketService.isConnected(this.connectionKey)) {
      unifiedWebSocketService.send(this.connectionKey, message);
    } else {
      // Queue the message for when connection is established
      this.messageQueue.push(message);
      // console.log('Writing WebSocket not connected, queuing message');
    }
  }

  private processMessageQueue() {
    if (this.connectionKey && unifiedWebSocketService.isConnected(this.connectionKey)) {
      while (this.messageQueue.length > 0) {
        const message = this.messageQueue.shift();
        if (message) {
          unifiedWebSocketService.send(this.connectionKey, message);
        }
      }
    }
  }

  private handleWebSocketMessage(data: WritingUpdate) {
    // console.log('Writing service received WebSocket message:', data);
    
    // Handle specific message types
    if (data.type === 'heartbeat') {
      // Respond to heartbeat
      this.sendMessage({
        type: 'pong',
        timestamp: Date.now()
      });
      return;
    }
    
    // Notify all registered callbacks
    this.notifyStatusCallbacks(data);
  }

  private notifyStatusCallbacks(update: WritingUpdate) {
    this.statusCallbacks.forEach(({ callback }) => {
      try {
        callback(update);
      } catch (error) {
        console.error('Error in writing status callback:', error);
      }
    });
  }

  public onStatusUpdate(callback: (update: WritingUpdate) => void): () => void {
    const callbackObj: StatusCallback = { callback };
    this.statusCallbacks.add(callbackObj);
    
    // Return unsubscribe function
    return () => {
      this.statusCallbacks.delete(callbackObj);
    };
  }

  private async getAccessToken(): Promise<string | null> {
    // Try to get token from various sources
    try {
      // Try auth store first
      const { useAuthStore } = await import('../../../features/auth/store');
      const token = useAuthStore.getState().getAccessToken();
      if (token) return token;
    } catch (error) {
      console.warn('Failed to get token from auth store:', error);
    }

    // Try cookies
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'access_token') {
        return decodeURIComponent(value);
      }
    }

    // Try localStorage
    const localToken = localStorage.getItem('access_token');
    if (localToken) return localToken;

    return null;
  }

  public isConnected(): boolean {
    return this.connectionKey ? unifiedWebSocketService.isConnected(this.connectionKey) : false;
  }

  public sendPing() {
    this.sendMessage({
      type: 'pong',
      timestamp: Date.now()
    });
  }
}

// Export singleton instance
export const writingWebSocketService = new WritingWebSocketService();