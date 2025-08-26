import React, { useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '../../chat/store'
import { useMissionStore } from '../store'
import { ResearchTabs } from './ResearchTabs'
import { Button } from '../../../components/ui/button'
import { PanelHeader } from '../../../components/ui/PanelHeader'
import { PanelControls } from '../../../components/ui/PanelControls'
import { usePanelControls } from '../../../components/layout/SplitPaneLayout'
import { useToast } from '../../../components/ui/toast'
import { useResearchWebSocket } from '../../../services/websocket'
import { apiClient } from '../../../config/api'
import { MissionHeaderStats } from '../../../components/mission'
import { ensureDate } from '../../../utils/timezone'
import { FileSearch, MessageSquare, Play, Square, RotateCcw } from 'lucide-react'

export const ResearchPanel: React.FC = () => {
  const { t } = useTranslation();
  const { activeChat } = useChatStore()
  const { missions, startMission, stopMission, resumeMission, fetchMissionStatus, ensureMissionInStore, missionLogs, setMissionLogs, appendMissionLogs } = useMissionStore()
  const { addToast } = useToast()
  const previousMissionId = useRef<string | null>(null)
  const [hasMoreLogs, setHasMoreLogs] = React.useState(false)
  const [isLoadingMoreLogs, setIsLoadingMoreLogs] = React.useState(false)
  const [totalLogsCount, setTotalLogsCount] = React.useState(0)
  
  let panelControls = null
  try {
    panelControls = usePanelControls()
  } catch {
    // Not in SplitPaneLayout context
  }

  const currentMission = activeChat?.missionId 
    ? missions.find(m => m.id === activeChat.missionId)
    : null

  const fetchInitialLogs = useCallback(async () => {
    if (!activeChat?.missionId) {
      return
    }
    
    try {
      const response = await apiClient.get(`/api/missions/${activeChat.missionId}/logs?skip=0&limit=1000`)
      if (response.data && response.data.logs) {
        const persistentLogs = response.data.logs.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))
        
        const sortedLogs = persistentLogs.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        setMissionLogs(activeChat.missionId, sortedLogs)
        
        setHasMoreLogs(response.data.has_more || false)
        setTotalLogsCount(response.data.total || sortedLogs.length)
      }
    } catch (error) {
      console.error(t('researchPanel.failedToFetchLogs'), error)
    }
  }, [activeChat?.missionId, setMissionLogs, t])

  const loadMoreLogs = useCallback(async () => {
    if (!activeChat?.missionId || !hasMoreLogs || isLoadingMoreLogs) {
      return
    }
    
    setIsLoadingMoreLogs(true)
    try {
      const currentLogs = missionLogs[activeChat.missionId] || []
      const skip = currentLogs.length
      
      const response = await apiClient.get(`/api/missions/${activeChat.missionId}/logs?skip=${skip}&limit=1000`)
      if (response.data && response.data.logs) {
        const newLogs = response.data.logs.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))
        
        const sortedNewLogs = newLogs.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        appendMissionLogs(activeChat.missionId, sortedNewLogs)
        
        setHasMoreLogs(response.data.has_more || false)
        setTotalLogsCount(response.data.total || (currentLogs.length + sortedNewLogs.length))
      }
    } catch (error) {
      console.error('Failed to load more logs:', error)
      addToast({
        type: 'error',
        title: t('researchPanel.failedToLoadMore'),
        message: t('researchPanel.pleaseTryAgain')
      })
    } finally {
      setIsLoadingMoreLogs(false)
    }
  }, [activeChat?.missionId, hasMoreLogs, isLoadingMoreLogs, missionLogs, appendMissionLogs, addToast, t])

  const loadAllLogs = useCallback(async () => {
    if (!activeChat?.missionId || !hasMoreLogs || isLoadingMoreLogs) {
      return
    }
    
    setIsLoadingMoreLogs(true)
    try {
      const response = await apiClient.get(`/api/missions/${activeChat.missionId}/logs?skip=0&limit=10000`)
      if (response.data && response.data.logs) {
        const allLogs = response.data.logs.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))
        
        const sortedAllLogs = allLogs.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        setMissionLogs(activeChat.missionId, sortedAllLogs)
        
        setHasMoreLogs(false)
        setTotalLogsCount(response.data.total || sortedAllLogs.length)
      }
    } catch (error) {
      console.error('Failed to load all logs:', error)
      addToast({
        type: 'error',
        title: t('researchPanel.failedToLoadAll'),
        message: t('researchPanel.pleaseTryAgain')
      })
    } finally {
      setIsLoadingMoreLogs(false)
    }
  }, [activeChat?.missionId, hasMoreLogs, isLoadingMoreLogs, setMissionLogs, addToast, t])

  const { isConnected, subscribeMission, unsubscribeMission } = useResearchWebSocket()
  
  useEffect(() => {
    if (activeChat?.missionId) {
      subscribeMission(activeChat.missionId)
      
      return () => {
        unsubscribeMission(activeChat.missionId)
      }
    }
  }, [activeChat?.missionId, subscribeMission, unsubscribeMission])

  useEffect(() => {
    const missionChanged = previousMissionId.current !== activeChat?.missionId
    
    if (missionChanged) {
      previousMissionId.current = activeChat?.missionId
      setHasMoreLogs(false)
      setTotalLogsCount(0)
    }
    
    if (activeChat?.missionId) {
      const loadMission = async () => {
        try {
          await ensureMissionInStore(activeChat.missionId!)
          if (missionChanged) {
            await fetchInitialLogs()
          }
        } catch (error) {
          console.error('Failed to load mission:', error)
        }
      }
      loadMission()
    }
  }, [activeChat?.missionId, fetchInitialLogs, ensureMissionInStore])

  useEffect(() => {
    if (!activeChat?.missionId || !currentMission) return

    const shouldPoll = currentMission.status === 'running'
    if (!shouldPoll) return

    const pollInterval = 15000

    const interval = setInterval(async () => {
      try {
        if (activeChat?.missionId) {
          await fetchMissionStatus(activeChat.missionId)
        }
      } catch (error) {
        console.error('Failed to poll mission status:', error)
      }
    }, pollInterval)

    return () => clearInterval(interval)
  }, [activeChat?.missionId, currentMission?.status, fetchMissionStatus])

  const handleStartMission = async () => {
    if (!activeChat?.missionId) return
    
    try {
      await startMission(activeChat.missionId)
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: t('researchPanel.missionStarted'),
        message: t('researchPanel.missionStartedSuccess'),
      })
    } catch (error) {
      console.error('Failed to start mission:', error)
      addToast({
        type: 'error',
        title: t('researchPanel.startFailed'),
        message: t('researchPanel.startFailedDescription'),
      })
    }
  }

  const handleStopMission = async () => {
    if (!activeChat?.missionId) return
    
    try {
      await stopMission(activeChat.missionId)
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: t('researchPanel.missionStopped'),
        message: t('researchPanel.missionStoppedSuccess'),
      })
    } catch (error) {
      console.error('Failed to stop mission:', error)
      addToast({
        type: 'error',
        title: t('researchPanel.stopFailed'),
        message: t('researchPanel.stopFailedDescription'),
      })
    }
  }

  const handleResumeMission = async () => {
    if (!activeChat?.missionId) return
    
    try {
      await resumeMission(activeChat.missionId)
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: t('researchPanel.missionResumed'),
        message: t('researchPanel.missionResumedSuccess'),
      })
    } catch (error) {
      console.error('Failed to resume mission:', error)
      addToast({
        type: 'error',
        title: t('researchPanel.resumeFailed'),
        message: t('researchPanel.resumeFailedDescription'),
      })
    }
  }

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'running':
        return 'bg-green-500'
      case 'paused':
        return 'bg-yellow-500'
      case 'stopped':
        return 'bg-destructive'
      case 'completed':
        return 'bg-primary'
      case 'pending':
        return 'bg-orange-500'
      case 'failed':
        return 'bg-destructive'
      default:
        return 'bg-muted'
    }
  }

  const getStatusText = (status?: string) => {
    switch (status) {
      case 'running':
        return t('researchPanel.running');
      case 'paused':
        return t('researchPanel.paused');
      case 'stopped':
        return t('researchPanel.stopped');
      case 'completed':
        return t('researchPanel.completed');
      case 'pending':
        return t('researchPanel.pending');
      case 'planning':
        return t('researchPanel.planning');
      case 'failed':
        return t('researchPanel.failed');
      default:
        return t('researchPanel.unknown');
    }
  }

  if (!activeChat?.missionId) {
    return (
      <div className="h-full flex items-center justify-center bg-background p-8">
        <div className="text-center max-w-md mx-auto">
          <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mx-auto mb-6">
            <FileSearch className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-medium text-foreground mb-2">
            {t('researchPanel.noActiveMission')}
          </h3>
          <p className="text-muted-foreground text-sm mb-6">
            {t('researchPanel.noActiveMissionDescription')}
          </p>
          <div className="flex items-center justify-center text-sm text-muted-foreground">
            <MessageSquare className="h-4 w-4 mr-2" />
            {t('researchPanel.askToResearch')}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background">
      <PanelHeader
        title={t('researchPanel.researchMission')}
        subtitle={
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div className={`w-2 h-2 rounded-full ${getStatusColor(currentMission?.status)}`}></div>
              <span className="text-sm text-muted-foreground">{getStatusText(currentMission?.status)}</span>
            </div>
            <MissionHeaderStats 
              logs={activeChat?.missionId ? (missionLogs[activeChat.missionId] || []) : []} 
              missionStatus={currentMission?.status} 
            />
          </div>
        }
        icon={<FileSearch className="h-5 w-5 text-primary" />}
        actions={
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              {currentMission?.status && (
                <>
                  {currentMission.status === 'running' && (
                    <Button
                      onClick={handleStopMission}
                      variant="destructive"
                      size="sm"
                      className="text-xs"
                    >
                      <Square className="h-3 w-3 mr-1" />
                      {t('researchPanel.stop')}
                    </Button>
                  )}
                  
                  {(currentMission.status === 'pending' || currentMission.status === 'planning') && (
                    <Button
                      onClick={handleStartMission}
                      variant="default"
                      size="sm"
                      className="text-xs"
                    >
                      <Play className="h-3 w-3 mr-1" />
                      {t('researchPanel.start')}
                    </Button>
                  )}
                  
                  {(currentMission.status === 'stopped' || currentMission.status === 'completed' || currentMission.status === 'failed') && (
                    <Button
                      onClick={handleResumeMission}
                      variant="outline"
                      size="sm"
                      className="text-xs"
                      disabled={currentMission.status === 'completed'}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      {currentMission.status === 'failed' ? t('researchPanel.retry') : t('researchPanel.resume')}
                    </Button>
                  )}
                </>
              )}
              
              {!currentMission?.status && (
                <div className="text-xs text-gray-400 italic">
                  {t('researchPanel.loadingMission')}
                </div>
              )}
            </div>
            
            <PanelControls
              onTogglePanel={panelControls?.toggleLeftPanel}
              isCollapsed={panelControls?.isLeftPanelCollapsed}
              showToggle={true}
              toggleTooltip={t('researchPanel.hideChatPanel')}
            />
          </div>
        }
      />

      <div className="flex-1 overflow-hidden p-6">
        <div className="h-full">
          <ResearchTabs 
            missionId={activeChat.missionId} 
            isWebSocketConnected={isConnected}
            hasMoreLogs={hasMoreLogs}
            onLoadMoreLogs={loadMoreLogs}
            onLoadAllLogs={loadAllLogs}
            isLoadingMoreLogs={isLoadingMoreLogs}
            totalLogsCount={totalLogsCount}
          />
        </div>
      </div>
    </div>
  )
}
