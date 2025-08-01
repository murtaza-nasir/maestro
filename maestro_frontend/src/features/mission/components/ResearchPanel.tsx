import React, { useEffect, useState, useCallback } from 'react'
import { useChatStore } from '../../chat/store'
import { useMissionStore, type Log } from '../store'
import { ResearchTabs } from './ResearchTabs'
import { Button } from '../../../components/ui/button'
import { PanelHeader } from '../../../components/ui/PanelHeader'
import { PanelControls } from '../../../components/ui/PanelControls'
import { usePanelControls } from '../../../components/layout/SplitPaneLayout'
import { useToast } from '../../../components/ui/toast'
import { useMissionWebSocket } from '../../../services/websocket'
import { apiClient } from '../../../config/api'
import { MissionHeaderStats } from '../../../components/mission'
import { ensureDate } from '../../../utils/timezone'
import { FileSearch, MessageSquare, Play, Square, RotateCcw } from 'lucide-react'

export const ResearchPanel: React.FC = () => {
  const { activeChat } = useChatStore()
  const { missions, startMission, stopMission, resumeMission, fetchMissionStatus, ensureMissionInStore, missionLogs, setMissionLogs } = useMissionStore()
  const { addToast } = useToast()
  const [logs, setLogs] = useState<Log[]>([])
  
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
      // Always fetch from database to get the complete persistent log history
      const response = await apiClient.get(`/api/missions/${activeChat.missionId}/logs`)
      if (response.data && response.data.logs) {
        const persistentLogs = response.data.logs.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))
        
        // Sort by timestamp
        persistentLogs.sort((a: Log, b: Log) => a.timestamp.getTime() - b.timestamp.getTime())
        
        // Set the logs directly from database - this is the authoritative source
        setLogs(persistentLogs)
        setMissionLogs(activeChat.missionId, persistentLogs)
        
        // console.log(`Loaded ${persistentLogs.length} logs from database for mission ${activeChat.missionId}`)
      }
    } catch (error) {
      console.error('Failed to fetch initial mission logs:', error)
      // If database fetch fails, fall back to existing in-memory logs
      if (activeChat?.missionId && missionLogs[activeChat.missionId]) {
        const fallbackLogs = missionLogs[activeChat.missionId].map(l => ({ ...l, timestamp: ensureDate(l.timestamp) }))
        setLogs(fallbackLogs)
        console.log(`Fell back to ${fallbackLogs.length} in-memory logs for mission ${activeChat.missionId}`)
      } else {
        setLogs([])
        console.log(`No logs available for mission ${activeChat.missionId}`)
      }
    }
  }, [activeChat?.missionId, missionLogs, setMissionLogs])

  // Handle WebSocket messages for real-time log updates
  const handleWebSocketMessage = useCallback((message: any) => {
    try {
      if (message.type === 'logs_update') {
        const newLogs: Log[] = message.data.map((log: any) => ({
          ...log,
          timestamp: ensureDate(log.timestamp),
        }))

        setLogs(prevLogs => {
          const updatedLogs = [...prevLogs, ...newLogs]
          // Use the mission_id from the message instead of activeChat
          if (message.mission_id) {
            setMissionLogs(message.mission_id, updatedLogs)
          }
          return updatedLogs
        })
      }
    } catch (error) {
      console.error('Error processing WebSocket message:', error)
    }
  }, [setMissionLogs]) // Remove activeChat dependency

  // Set up WebSocket connection for real-time updates using centralized service
  const { isConnected, subscribe } = useMissionWebSocket(activeChat?.missionId || null)

  // Subscribe to logs updates via centralized WebSocket service
  useEffect(() => {
    if (!isConnected) return

    const unsubscribe = subscribe('logs_update', handleWebSocketMessage)
    return unsubscribe
  }, [activeChat?.missionId, isConnected, subscribe, handleWebSocketMessage])

  // Subscribe to status updates via centralized WebSocket service
  useEffect(() => {
    if (!isConnected) return

    const unsubscribe = subscribe('status_update', (message: any) => {
      if (import.meta.env.DEV) {
        console.log('Status update received:', message)
      }
      
      if (message.mission_id === activeChat?.missionId && message.data) {
        const { updateMissionStatus } = useMissionStore.getState()
        updateMissionStatus(message.mission_id, message.data.status)
      }
    })

    return unsubscribe
  }, [activeChat?.missionId, isConnected, subscribe])

  // Ensure mission is loaded and fetch status when chat changes
  useEffect(() => {
    if (activeChat?.missionId) {
      const loadMission = async () => {
        try {
          await ensureMissionInStore(activeChat.missionId!)
          await fetchMissionStatus(activeChat.missionId!)
          await fetchInitialLogs()
        } catch (error) {
          console.error('Failed to load mission:', error)
        }
      }
      loadMission()
    }
  }, [activeChat?.missionId]) // Removed unstable function dependencies

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
              logs={logs} 
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
          <ResearchTabs missionId={activeChat.missionId} />
        </div>
      </div>
    </div>
  )
}
