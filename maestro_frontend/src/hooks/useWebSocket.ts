/**
 * Generic WebSocket Hook - now delegates to UnifiedWebSocketService
 * @deprecated Use unifiedWebSocketService directly for new code
 */
import { useEffect, useRef, useCallback, useState } from 'react';
import { unifiedWebSocketService, useUnifiedWebSocket } from '../services/unifiedWebSocketService';

export const useWebSocket = (url: string, onMessage?: (data: any) => void) => {
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [isConnected, setIsConnected] = useState(false);
  
  // Use unified WebSocket hook
  const unified = useUnifiedWebSocket({
    endpoint: url,
    connectionType: 'research', // Default to research for backward compatibility
    onMessage: (data) => {
      setLastMessage(data);
      if (onMessage) {
        onMessage(data);
      }
    },
    onConnect: () => {
      setIsConnected(true);
    },
    onDisconnect: () => {
      setIsConnected(false);
    }
  });
  
  // Provide backward-compatible interface
  const reconnect = useCallback(() => {
    // Unified service handles reconnection automatically
    // console.log('Reconnection is handled automatically by UnifiedWebSocketService');
  }, []);

  return {
    isConnected: unified.isConnected,
    lastMessage,
    reconnect
  };
};