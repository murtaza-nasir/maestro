import React from 'react'
import { useParams } from 'react-router-dom'
import { useChatStore } from '../store'
import { SplitPaneLayout } from '../../../components/layout/SplitPaneLayout'
import { ChatPanel } from './ChatPanel'
import { ResearchPanel } from '../../mission/components'

interface ChatViewProps {
  chatId?: string
}

export const ChatView: React.FC<ChatViewProps> = ({ chatId: propChatId }) => {
  const { chatId: paramChatId } = useParams<{ chatId: string }>()
  const chatId = propChatId || paramChatId
  
  const { activeChat } = useChatStore()

  // Determine if we should show the research panel
  const showResearchPanel = Boolean(activeChat?.missionId)

  // Use activeChat.id as the key to force new component instances for different chats
  // Include a timestamp for new chats to ensure they get fresh instances
  const chatPanelKey = activeChat?.id || `new-chat-${Date.now()}`

  return (
    <SplitPaneLayout
      leftPanel={<ChatPanel key={chatPanelKey} chatId={chatId} />}
      rightPanel={<ResearchPanel />}
      defaultLeftWidth={50}
      minLeftWidth={30}
      maxLeftWidth={80}
      showRightPanel={showResearchPanel}
    />
  )
}
