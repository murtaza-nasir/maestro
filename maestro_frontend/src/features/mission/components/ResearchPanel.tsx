import React, { useEffect, useCallback, useRef } from 'react'
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
  const { activeChat } = useChatStore()
  const { missions, startMission, stopMission, resumeMission, fetchMissionStatus, ensureMissionInStore, missionLogs, setMissionLogs, appendMissionLogs } = useMissionStore()
  const { addToast } = useToast()
  const previousMissionId = useRef<string | null>(null)
  const [hasMoreLogs, setHasMoreLogs] = React.useState(false)
  const [isLoadingMoreLogs, setIsLoadingMoreLogs] = React.useState(false)
  const [totalLogsCount, setTotalLogsCount] = React.useState(0)
  
  // Get panel controls - use try/catch to handle when not in SplitPaneLayout context
  let panelControls = null
  try {
    panelControls = usePanelControls()
  } catch {
    // Not in SplitPaneLayout context, controls will be disabled
  }

  // Get the current mission from the missions array using the chat's missionId
  const currentMission = activeChat?.missionId 
    ? missions.find(m => m.id === activeChat.missionId)
    : null

  // Fetch initial logs for the mission - always fetch from database to get persistent logs
  const fetchInitialLogs = useCallback(async () => {
    if (!activeChat?.missionId) {
      return
    }
    
    try {
      // Fetch initial batch of logs with pagination support (1000 at a time)
      const response = await apiClient.get(`/api/missions/${activeChat.missionId}/logs?skip=0&limit=1000`)
      if (response.data && response.data.logs) {
        const persistentLogs = response.data.logs.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))
        
        // Sort logs by timestamp (newest first, then reverse for chronological order)
        const sortedLogs = persistentLogs.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        setMissionLogs(activeChat.missionId, sortedLogs)
        
        // Update pagination state
        setHasMoreLogs(response.data.has_more || false)
        setTotalLogsCount(response.data.total || sortedLogs.length)
        
        // console.log(`Loaded ${persistentLogs.length} logs from database (total: ${response.data.total})`)
      }
    } catch (error) {
      console.error('Failed to fetch initial mission logs:', error)
      // If database fetch fails, just log the error
      console.log(`Failed to fetch logs for mission ${activeChat.missionId}`)
    }
  }, [activeChat?.missionId, setMissionLogs])

  // Load more logs function
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
        
        // Sort new logs by timestamp
        const sortedNewLogs = newLogs.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
        
        // Append new logs to existing ones
        appendMissionLogs(activeChat.missionId, sortedNewLogs)
        
        // Update pagination state
        setHasMoreLogs(response.data.has_more || false)
        setTotalLogsCount(response.data.total || (currentLogs.length + sortedNewLogs.length))
        
        // console.log(`Loaded ${sortedNewLogs.length} more logs (total now: ${currentLogs.length + sortedNewLogs.length})`)
      }
    } catch (error) {
      console.error('Failed to load more logs:', error)
      addToast({
        type: 'error',
        title: 'Failed to load more logs',
        message: 'Please try again'
      })
    } finally {
      setIsLoadingMoreLogs(false)
    }
  }, [activeChat?.missionId, hasMoreLogs, isLoadingMoreLogs, missionLogs, appendMissionLogs, addToast])

  // Set up single WebSocket connection for ALL research updates
  const { isConnected, subscribeMission, unsubscribeMission } = useResearchWebSocket()
  
  // Subscribe/unsubscribe to mission when it changes
  useEffect(() => {
    if (activeChat?.missionId) {
      subscribeMission(activeChat.missionId)
      
      // Properly unsubscribe when mission changes or component unmounts
      return () => {
        unsubscribeMission(activeChat.missionId)
      }
    }
  }, [activeChat?.missionId, subscribeMission, unsubscribeMission])

  // No need for WebSocket event subscriptions here anymore!
  // The ResearchWebSocketService handles all mission-specific updates at the service level
  // when subscribeMission/unsubscribeMission is called

  // Ensure mission is loaded and fetch status when chat changes
  useEffect(() => {
    // Check if mission actually changed
    const missionChanged = previousMissionId.current !== activeChat?.missionId
    
    if (missionChanged) {
      // console.log(`Mission changed from ${previousMissionId.current} to ${activeChat?.missionId}`)
      previousMissionId.current = activeChat?.missionId
      // Reset pagination state when mission changes
      setHasMoreLogs(false)
      setTotalLogsCount(0)
    }
    
    if (activeChat?.missionId) {
      const loadMission = async () => {
        try {
          // ensureMissionInStore already fetches status, so we don't need to call fetchMissionStatus
          await ensureMissionInStore(activeChat.missionId!)
          // Only fetch initial logs if mission changed
          if (missionChanged) {
            await fetchInitialLogs()
          }
        } catch (error) {
          console.error('Failed to load mission:', error)
        }
      }
      loadMission()
    }
  }, [activeChat?.missionId, fetchInitialLogs]) // Added fetchInitialLogs dependency

  // Minimal polling - only for actively running missions, rely on WebSocket for most updates
  useEffect(() => {
    if (!activeChat?.missionId || !currentMission) return

    // Only poll for actively running missions, not pending/planning
    const shouldPoll = currentMission.status === 'running'
    if (!shouldPoll) return

    // Use much longer interval - WebSocket should handle most updates
    const pollInterval = 15000 // 15 seconds for running missions only

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
      // Refresh mission status to ensure UI updates
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: 'Mission Started',
        message: 'The research mission has been started successfully.',
      })
    } catch (error) {
      console.error('Failed to start mission:', error)
      addToast({
        type: 'error',
        title: 'Start Failed',
        message: 'Failed to start the mission. Please try again.',
      })
    }
  }

  const handleStopMission = async () => {
    if (!activeChat?.missionId) return
    
    try {
      await stopMission(activeChat.missionId)
      // Refresh mission status to ensure UI updates
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: 'Mission Stopped',
        message: 'The research mission has been stopped successfully.',
      })
    } catch (error) {
      console.error('Failed to stop mission:', error)
      addToast({
        type: 'error',
        title: 'Stop Failed',
        message: 'Failed to stop the mission. Please try again.',
      })
    }
  }

  const handleResumeMission = async () => {
    if (!activeChat?.missionId) return
    
    try {
      await resumeMission(activeChat.missionId)
      // Refresh mission status to ensure UI updates
      await fetchMissionStatus(activeChat.missionId)
      addToast({
        type: 'success',
        title: 'Mission Resumed',
        message: 'The research mission has been resumed successfully.',
      })
    } catch (error) {
      console.error('Failed to resume mission:', error)
      addToast({
        type: 'error',
        title: 'Resume Failed',
        message: 'Failed to resume the mission. Please try again.',
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
        return 'Running'
      case 'paused':
        return 'Paused'
      case 'stopped':
        return 'Stopped'
      case 'completed':
        return 'Completed'
      case 'pending':
        return 'Pending'
      case 'planning':
        return 'Planning'
      case 'failed':
        return 'Failed'
      default:
        return 'Unknown'
    }
  }

  // Show placeholder if no active mission
  if (!activeChat?.missionId) {
    return (
      <div className="h-full flex items-center justify-center bg-background p-8">
        <div className="text-center max-w-md mx-auto">
          <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mx-auto mb-6">
            <FileSearch className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-medium text-foreground mb-2">
            No Active Research Mission
          </h3>
          <p className="text-muted-foreground text-sm mb-6">
            Start a research conversation in the chat to see mission progress, plans, notes, and drafts here.
          </p>
          <div className="flex items-center justify-center text-sm text-muted-foreground">
            <MessageSquare className="h-4 w-4 mr-2" />
            Ask me to research a topic to get started
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Research Panel Header */}
      <PanelHeader
        title="Research Mission"
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
                  {/* Running state: Show Stop */}
                  {currentMission.status === 'running' && (
                    <Button
                      onClick={handleStopMission}
                      variant="destructive"
                      size="sm"
                      className="text-xs"
                    >
                      <Square className="h-3 w-3 mr-1" />
                      Stop
                    </Button>
                  )}
                  
                  {/* Pending or Planning state: Show Start */}
                  {(currentMission.status === 'pending' || currentMission.status === 'planning') && (
                    <Button
                      onClick={handleStartMission}
                      variant="default"
                      size="sm"
                      className="text-xs"
                    >
                      <Play className="h-3 w-3 mr-1" />
                      Start
                    </Button>
                  )}
                  
                  {/* Stopped, Completed, or Failed state: Show Resume/Retry */}
                  {(currentMission.status === 'stopped' || currentMission.status === 'completed' || currentMission.status === 'failed') && (
                    <Button
                      onClick={handleResumeMission}
                      variant="outline"
                      size="sm"
                      className="text-xs"
                      disabled={currentMission.status === 'completed'}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      {currentMission.status === 'failed' ? 'Retry' : 'Resume'}
                    </Button>
                  )}
                </>
              )}
              
              {/* Show placeholder when mission status is unknown */}
              {!currentMission?.status && (
                <div className="text-xs text-gray-400 italic">
                  Loading mission...
                </div>
              )}
            </div>
            
            <PanelControls
              onTogglePanel={panelControls?.toggleLeftPanel}
              isCollapsed={panelControls?.isLeftPanelCollapsed}
              showToggle={true}
              toggleTooltip="Hide Chat Panel"
            />
          </div>
        }
      />

      {/* Research Tabs Content */}
      <div className="flex-1 overflow-hidden p-6">
        <div className="h-full">
          <ResearchTabs 
            missionId={activeChat.missionId} 
            isWebSocketConnected={isConnected}
            hasMoreLogs={hasMoreLogs}
            onLoadMoreLogs={loadMoreLogs}
            isLoadingMoreLogs={isLoadingMoreLogs}
            totalLogsCount={totalLogsCount}
          />
        </div>
      </div>
    </div>
  )
}
