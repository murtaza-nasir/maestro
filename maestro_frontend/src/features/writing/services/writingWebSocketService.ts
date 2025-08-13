
export interface WritingUpdate {
  type: 'agent_status' | 'draft_content_update' | 'connection_established' | 'pong' | 'chat_title_update' | 'stats_update' | 'heartbeat' | 'connection_lost';
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
  private websocket: WebSocket | null = null;
  private statusCallbacks: Set<StatusCallback> = new Set();
  private currentSessionId: string | null = null;
  private pingInterval: number | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private messageQueue: WritingUpdate[] = [];
  private isIntentionalDisconnect: boolean = false;

  constructor() {
    // Don't auto-connect on construction
  }

  public async connectToSession(sessionId: string) {
    // Disconnect from previous session if any
    if (this.websocket && this.currentSessionId !== sessionId) {
      this.disconnect();
    }

    // Don't reconnect if already connected to the same session
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN && this.currentSessionId === sessionId) {
      return;
    }

    this.currentSessionId = sessionId;
    this.isIntentionalDisconnect = false;
    this.reconnectAttempts = 0;
    await this.connectWebSocket(sessionId);
  }

  private async connectWebSocket(sessionId: string) {
    try {
      const accessToken = await this.getAccessToken();
      if (!accessToken) {
        console.warn('Cannot connect to writing WebSocket: missing access token');
        return;
      }

      // Build WebSocket URL using nginx proxy (same origin)
      let wsBaseUrl = import.meta.env.VITE_API_WS_URL;
      
      // If no WebSocket URL is set, use relative URL (same origin through nginx proxy)
      if (!wsBaseUrl) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsBaseUrl = `${protocol}//${window.location.host}`;
      }
      
      const wsUrl = `${wsBaseUrl}/ws/${sessionId}?token=${encodeURIComponent(accessToken)}`;
      
      console.log('Attempting to connect to writing WebSocket:', wsUrl);
      
      this.websocket = new WebSocket(wsUrl);
      
      this.websocket.onopen = () => {
        console.log('Writing WebSocket connected successfully to session:', sessionId);
        this.reconnectAttempts = 0; // Reset reconnect attempts on successful connection
        
        // Start ping interval to keep connection alive
        this.startPingInterval();
        
        // Process any queued messages
        this.processMessageQueue();
      };
      
      this.websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Writing WebSocket message received:', data);
          this.handleWebSocketMessage(data);
        } catch (error) {
          console.error('Error parsing writing WebSocket message:', error);
        }
      };
      
      this.websocket.onclose = (event) => {
        console.log('Writing WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
        this.websocket = null;
        this.stopPingInterval();
        
        // Only attempt to reconnect if it's not intentional and we still have a session
        if (!this.isIntentionalDisconnect && event.code !== 1008 && this.currentSessionId) { // 1008 = Policy Violation (auth failure)
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000); // Exponential backoff, max 30s
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms...`);
            setTimeout(() => {
              if (this.currentSessionId && !this.isIntentionalDisconnect) {
                this.connectWebSocket(this.currentSessionId);
              }
            }, delay);
          } else {
            console.error('Max reconnection attempts reached. Please refresh the page.');
            // Notify callbacks about disconnection
            this.notifyDisconnection();
          }
        }
      };
      
      this.websocket.onerror = (error) => {
        console.error('Writing WebSocket error:', error);
        console.error('Failed to connect to:', wsUrl);
      };
    } catch (error) {
      console.error('Error creating writing WebSocket connection:', error);
    }
  }

  private async getAccessToken(): Promise<string | null> {
    try {
      // Try to get from auth store first
      const authStore = (window as any).__AUTH_STORE__;
      if (authStore && authStore.getState) {
        const token = authStore.getState().accessToken;
        if (token) return token;
      }

      // Fallback to localStorage
      const token = localStorage.getItem('access_token');
      if (token) return token;

      // Fallback to cookies
      const cookies = document.cookie.split(';');
      for (const cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'access_token') {
          return value;
        }
      }

      return null;
    } catch (error) {
      console.error('Error getting access token:', error);
      return null;
    }
  }

  private handleWebSocketMessage(data: WritingUpdate) {
    console.log('Writing service received WebSocket message:', data);
    
    // Handle heartbeat messages silently (just acknowledge them)
    if (data.type === 'heartbeat') {
      console.debug('Received heartbeat from server');
      return; // Don't notify callbacks for heartbeats
    }
    
    // Notify all status callbacks
    this.statusCallbacks.forEach(({ callback }) => {
      try {
        callback(data);
      } catch (error) {
        console.error('Error in writing status callback:', error);
      }
    });
  }

  public onStatusUpdate(callback: (update: WritingUpdate) => void): () => void {
    const statusCallback: StatusCallback = { callback };
    this.statusCallbacks.add(statusCallback);
    
    // Return unsubscribe function
    return () => {
      this.statusCallbacks.delete(statusCallback);
    };
  }

  public sendPing() {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify({
        type: 'ping',
        timestamp: Date.now()
      }));
    }
  }

  public sendAgentStatus(status: string) {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify({
        type: 'agent_status',
        status: status
      }));
    }
  }

  public disconnect() {
    this.isIntentionalDisconnect = true;
    this.stopPingInterval();
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.statusCallbacks.clear();
    this.currentSessionId = null;
    this.messageQueue = [];
    this.reconnectAttempts = 0;
  }

  public isConnected(): boolean {
    return this.websocket !== null && this.websocket.readyState === WebSocket.OPEN;
  }

  public getCurrentSessionId(): string | null {
    return this.currentSessionId;
  }

  private startPingInterval() {
    this.stopPingInterval(); // Clear any existing interval
    
    // Send ping every 25 seconds (server sends heartbeat every 30s)
    this.pingInterval = window.setInterval(() => {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        const pingMessage = JSON.stringify({
          type: 'ping',
          timestamp: Date.now()
        });
        console.debug('Sending ping to keep connection alive');
        this.websocket.send(pingMessage);
      }
    }, 25000);
  }
  
  private stopPingInterval() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
  
  private processMessageQueue() {
    // Process any messages that were queued while disconnected
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      if (message) {
        this.handleWebSocketMessage(message);
      }
    }
  }
  
  private notifyDisconnection() {
    // Notify all callbacks about disconnection
    const disconnectMessage: WritingUpdate = {
      type: 'connection_lost' as any,
      timestamp: Date.now()
    };
    this.statusCallbacks.forEach(({ callback }) => {
      try {
        callback(disconnectMessage);
      } catch (error) {
        console.error('Error in status callback:', error);
      }
    });
  }
  
  public sendMessage(message: any) {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, attempting to reconnect...');
      // Try to reconnect if we have a session
      if (this.currentSessionId && !this.isIntentionalDisconnect) {
        this.connectWebSocket(this.currentSessionId);
      }
    }
  }
}

// Singleton instance
export const writingWebSocketService = new WritingWebSocketService();
