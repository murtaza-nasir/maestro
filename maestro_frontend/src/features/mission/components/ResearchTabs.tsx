import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../../components/ui/tabs'
import { useMissionStore } from '../store'
import { PlanTab } from './PlanTab'
import { NotesTab } from './NotesTab'
import { DraftTab } from './DraftTab'
import { AgentsTab } from './AgentsTab'
import { GoalPadTab } from './GoalPadTab'
import { ScratchpadTab } from './ScratchpadTab'
import { ThoughtPadTab } from './ThoughtPadTab'
import { FileText, BookOpen, Edit3, Bot, } from 'lucide-react'

interface ResearchTabsProps {
  missionId: string
  isWebSocketConnected?: boolean
  hasMoreLogs?: boolean
  onLoadMoreLogs?: () => void
  onLoadAllLogs?: () => void
  isLoadingMoreLogs?: boolean
  totalLogsCount?: number
}

export const ResearchTabs: React.FC<ResearchTabsProps> = ({ 
  missionId, 
  hasMoreLogs,
  onLoadMoreLogs,
  onLoadAllLogs,
  isLoadingMoreLogs,
  totalLogsCount
}) => {
  const { t } = useTranslation();
  const { activeTab, setActiveTab, ensureMissionInStore, missionContexts, fetchMissionContext } = useMissionStore()
  const [activePlanTab, setActivePlanTab] = useState('outline')
  
  const missionContext = missionContexts[missionId] || null

  useEffect(() => {
    if (missionId) {
      ensureMissionInStore(missionId)
      if (!missionContext) {
        fetchMissionContext(missionId)
      }
    }
  }, [missionId, ensureMissionInStore, fetchMissionContext, missionContext])

  return (
    <div className="w-full h-full flex flex-col">
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="h-full flex flex-col">
        <TabsList className="grid w-full grid-cols-4 flex-shrink-0 bg-secondary">
          <TabsTrigger value="plan" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline">{t('researchTabs.plan')}</span>
          </TabsTrigger>
          <TabsTrigger value="agents" className="flex items-center gap-2">
            <Bot className="h-4 w-4" />
            <span className="hidden sm:inline">{t('researchTabs.agents')}</span>
          </TabsTrigger>
          <TabsTrigger value="notes" className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            <span className="hidden sm:inline">{t('researchTabs.notes')}</span>
          </TabsTrigger>
          <TabsTrigger value="draft" className="flex items-center gap-2">
            <Edit3 className="h-4 w-4" />
            <span className="hidden sm:inline">{t('researchTabs.draft')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="plan" className="mt-2 flex-1 overflow-auto">
          <Tabs value={activePlanTab} onValueChange={setActivePlanTab} className="h-full flex flex-col">
            <TabsList className="grid w-full grid-cols-4 bg-secondary">
              <TabsTrigger value="outline">{t('researchTabs.outline')}</TabsTrigger>
              <TabsTrigger value="goal_pad">{t('researchTabs.goalPad')}</TabsTrigger>
              <TabsTrigger value="scratchpad">{t('researchTabs.scratchpad')}</TabsTrigger>
              <TabsTrigger value="thought_pad">{t('researchTabs.thoughtPad')}</TabsTrigger>
            </TabsList>
            <TabsContent value="outline" className="mt-2 flex-1 overflow-auto">
              <PlanTab missionId={missionId} />
            </TabsContent>
            <TabsContent value="goal_pad" className="mt-2 flex-1 overflow-auto">
              <GoalPadTab goals={missionContext?.goal_pad || []} />
            </TabsContent>
            <TabsContent value="scratchpad" className="mt-2 flex-1 overflow-auto">
              <ScratchpadTab scratchpad={missionContext?.agent_scratchpad || null} />
            </TabsContent>
            <TabsContent value="thought_pad" className="mt-2 flex-1 overflow-auto">
              <ThoughtPadTab thoughts={missionContext?.thought_pad || []} />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="agents" className="mt-2 flex-1 overflow-auto">
          <AgentsTab 
            missionId={missionId}
            hasMoreLogs={hasMoreLogs}
            onLoadMoreLogs={onLoadMoreLogs}
            onLoadAllLogs={onLoadAllLogs}
            isLoadingMoreLogs={isLoadingMoreLogs}
            totalLogsCount={totalLogsCount}
          />
        </TabsContent>

        <TabsContent value="notes" className="mt-2 flex-1 overflow-auto">
          <NotesTab missionId={missionId} />
        </TabsContent>

        <TabsContent value="draft" className="mt-2 flex-1 overflow-auto">
          <DraftTab missionId={missionId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
