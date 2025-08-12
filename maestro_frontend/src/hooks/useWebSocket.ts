import { useEffect, useRef, useCallback, useState } from 'react';
import { useAuthStore } from '../features/auth/store';

export const useWebSocket = (url: string, onMessage?: (data: any) => void) => {
  const { accessToken } = useAuthStore.getState();
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3; // Reduced from 5
  const isConnecting = useRef(false);

  // Use a ref to store the latest onMessage callback without causing reconnections
  const onMessageRef = useRef(onMessage);
  
  // Update the ref when onMessage changes, but don't trigger reconnections
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);
  
  // Create a stable callback that always calls the latest onMessage
  const stableOnMessage = useCallback((data: any) => {
    if (onMessageRef.current) {
      onMessageRef.current(data);
    }
  }, []); // No dependencies - this callback is truly stable

  const connect = useCallback(() => {
    if (!url || !accessToken || isConnecting.current || url.trim() === '') {
      return;
    }

    // Prevent multiple connection attempts
    isConnecting.current = true;

    // Clean up existing connection
    if (ws.current) {
      ws.current.close();
    }

    try {
      // Build WebSocket URL using nginx proxy (same origin)
      let wsBaseUrl = import.meta.env.VITE_API_WS_URL;
      if (!wsBaseUrl) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsBaseUrl = `${protocol}//${window.location.host}`;
      }
      const wsUrl = `${wsBaseUrl}${url}?token=${encodeURIComponent(accessToken)}`;
      
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        // Only log connection in development mode
        if (import.meta.env.DEV) {
          console.log('WebSocket connected to:', url);
        }
        reconnectAttempts.current = 0;
        isConnecting.current = false;
        setIsConnected(true);
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      isConnecting.current = false;
      setIsConnected(false);
      return;
    }

    ws.current.onmessage = (event) => {
      try {
        // Check if the data is already a JSON string or an object
        let data;
        if (typeof event.data === 'string') {
          // If it's a string, try to parse it as JSON
          try {
            data = JSON.parse(event.data);
          } catch (parseError) {
            // If parsing fails, treat it as a plain string message
            console.warn('WebSocket message is not valid JSON, treating as string:', event.data);
            data = { type: 'message', data: event.data };
          }
        } else if (typeof event.data === 'object') {
          // If it's already an object, use it directly
          data = event.data;
        } else {
          // For any other type, convert to string and wrap
          data = { type: 'message', data: String(event.data) };
        }
        
        setLastMessage(data);
        stableOnMessage(data);
      } catch (error) {
        console.error('Error processing WebSocket message:', error, 'Raw data:', event.data);
      }
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error for', url, ':', error);
    };

    ws.current.onclose = (event) => {
      isConnecting.current = false;
      setIsConnected(false);
      
      if (import.meta.env.DEV) {
        console.log('WebSocket disconnected from:', url, 'Code:', event.code);
      }
      
      // Attempt to reconnect if it wasn't a clean close and we haven't exceeded max attempts
      if (event.code !== 1000 && reconnectAttempts.current < maxReconnectAttempts) {
        reconnectAttempts.current++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000); // Exponential backoff, max 10s (reduced from 30s)
        
        if (import.meta.env.DEV) {
          console.log(`Attempting to reconnect to ${url} in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`);
        }
        
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };
  }, [url, accessToken, stableOnMessage]);

  useEffect(() => {
    // Only connect if we have a valid URL
    if (url && url.trim() !== '') {
      connect();
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (ws.current) {
        ws.current.close(1000, 'Component unmounting'); // Clean close
      }
    };
  }, [connect, url]);

  // Return connection status, last message, and manual reconnect function
  return {
    isConnected,
    lastMessage,
    reconnect: connect
  };
};
