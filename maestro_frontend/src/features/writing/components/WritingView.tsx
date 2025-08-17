import React, { useEffect } from 'react'
import { SplitPaneLayout } from '../../../components/layout/SplitPaneLayout'
import { WritingChatPanel } from './WritingChatPanel'
import { DraftPanel } from './DraftPanel'
import { useWritingStore } from '../store'

export const WritingView: React.FC = () => {
  const { 
    disconnectWebSocket, 
    connectWebSocket, 
    currentSession,
    activeChat,
    getSessionLoading,
    setSessionLoading,
    setAgentStatus,
    getCurrentMessages
  } = useWritingStore()
  
  // Reconnect WebSocket when component mounts and disconnect when unmounts
  useEffect(() => {
    // On mount: reconnect if we have an active session
    // For writing WebSocket, we need the writing session ID, not the chat ID
    const sessionId = currentSession?.id
    if (sessionId) {
      // console.log('WritingView mounting - reconnecting Writing WebSocket for session:', sessionId)
      connectWebSocket(sessionId)
      
      // Check if we need to clear stuck loading state
      // This happens when a response completed while we were away
      const messages = getCurrentMessages()
      if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1]
        if (lastMessage.role === 'assistant') {
          // If last message is from assistant but we're still showing loading, clear it
          const isLoading = getSessionLoading(sessionId)
          if (isLoading) {
            // console.log('Clearing stuck loading state after reconnecting to WritingView')
            setSessionLoading(sessionId, false)
            setAgentStatus(sessionId, 'idle')
            
            // Also clear for activeChat if different
            if (activeChat?.id && activeChat.id !== sessionId) {
              setSessionLoading(activeChat.id, false)
              setAgentStatus(activeChat.id, 'idle')
            }
          }
        }
      }
    }
    
    // On unmount: disconnect
    return () => {
      // console.log('WritingView unmounting - disconnecting Writing WebSocket')
      disconnectWebSocket()
    }
  }, [currentSession?.id]) // Re-run if session changes
  
  return (
    <SplitPaneLayout
      leftPanel={<WritingChatPanel />}
      rightPanel={<DraftPanel />}
      defaultLeftWidth={50}
      minLeftWidth={30}
      maxLeftWidth={80}
      showRightPanel={true}
    />
  )
}
