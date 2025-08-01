import React from 'react'
import { SplitPaneLayout } from '../../../components/layout/SplitPaneLayout'
import { WritingChatPanel } from './WritingChatPanel'
import { DraftPanel } from './DraftPanel'

export const WritingView: React.FC = () => {
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
