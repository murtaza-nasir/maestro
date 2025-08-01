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

  return (
    <SplitPaneLayout
      leftPanel={<ChatPanel chatId={chatId} />}
      rightPanel={<ResearchPanel />}
      defaultLeftWidth={50}
      minLeftWidth={30}
      maxLeftWidth={80}
      showRightPanel={showResearchPanel}
    />
  )
}
