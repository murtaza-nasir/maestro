
export interface WritingUpdate {
  type: 'agent_status' | 'draft_content_update' | 'connection_established' | 'pong' | 'chat_title_update' | 'stats_update';
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

  constructor() {
    // Don't auto-connect on construction
  }

  public async connectToSession(sessionId: string) {
    // Disconnect from previous session if any
    if (this.websocket && this.currentSessionId !== sessionId) {
      this.disconnect();
    }

    // Don't reconnect if already connected to the same session
    if (this.websocket && this.currentSessionId === sessionId) {
      return;
    }

    this.currentSessionId = sessionId;
    await this.connectWebSocket(sessionId);
  }

  private async connectWebSocket(sessionId: string) {
    try {
      const accessToken = await this.getAccessToken();
      if (!accessToken) {
        console.warn('Cannot connect to writing WebSocket: missing access token');
        return;
      }

      // Build WebSocket URL using environment variables
      let wsBaseUrl = import.meta.env.VITE_API_WS_URL;
      
      // If no WebSocket URL is set, derive it from the API base URL
      if (!wsBaseUrl) {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';
        wsBaseUrl = apiBaseUrl.replace(/^http/, 'ws');
      }
      
      const wsUrl = `${wsBaseUrl}/ws/${sessionId}?token=${encodeURIComponent(accessToken)}`;
      
      console.log('Attempting to connect to writing WebSocket:', wsUrl);
      
      this.websocket = new WebSocket(wsUrl);
      
      this.websocket.onopen = () => {
        console.log('Writing WebSocket connected successfully to session:', sessionId);
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
        
        // Only attempt to reconnect if it's not a permanent failure and we still have a session
        if (event.code !== 1008 && this.currentSessionId) { // 1008 = Policy Violation (auth failure)
          setTimeout(() => {
            if (this.currentSessionId) {
              this.connectWebSocket(this.currentSessionId);
            }
          }, 3000);
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
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.statusCallbacks.clear();
    this.currentSessionId = null;
  }

  public isConnected(): boolean {
    return this.websocket !== null && this.websocket.readyState === WebSocket.OPEN;
  }

  public getCurrentSessionId(): string | null {
    return this.currentSessionId;
  }
}

// Singleton instance
export const writingWebSocketService = new WritingWebSocketService();
