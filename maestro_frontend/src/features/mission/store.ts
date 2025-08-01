import { create } from 'zustand'
import { apiClient } from '../../config/api'
import { ensureDate } from '../../utils/timezone'
import { missionDB } from '../../utils/storageUtils'

export interface Note {
  note_id: string
  content: string
  source?: string
  url?: string
  timestamp: Date
  tags?: string[]
}

export interface MissionContext {
  goal_pad: any[]
  thought_pad: any[]
  agent_scratchpad: string | null
}

export interface Log {
  timestamp: Date;
  agent_name: string;
  action: string;
  status: 'success' | 'failure' | 'running' | 'warning';
  output_summary?: string;
  error_message?: string;
}

interface Mission {
  id: string
  request: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'stopped' | 'planning'
  plan?: string
  notes?: Note[]
  logs?: Log[]
  draft?: string
  report?: string
  stats?: {
    total_cost: number
    total_tokens: number
    tool_usage: Record<string, number>
  }
  createdAt: Date
  updatedAt: Date
}

interface MissionState {
  missions: Mission[]
  activeMission: Mission | null
  missionLogs: { [missionId: string]: Log[] };
  missionContexts: { [missionId: string]: MissionContext };
  activeTab: 'plan' | 'notes' | 'draft' | 'agents'
  isLoaded: boolean
  createMission: (request: string, options?: { useWebSearch?: boolean; documentGroupId?: string; chatId?: string }) => Promise<Mission>
  startMission: (missionId: string) => Promise<void>
  stopMission: (missionId: string) => Promise<void>
  resumeMission: (missionId: string) => Promise<void>
  updateMissionStatus: (missionId: string, status: Mission['status']) => void
  setMissionPlan: (missionId: string, plan: string) => void
  setMissionNotes: (missionId: string, notes: Note[]) => void
  appendMissionNotes: (missionId: string, newNotes: Note[]) => void
  setMissionLogs: (missionId: string, logs: Log[]) => void
  setMissionDraft: (missionId: string, draft: string) => void
  updateMissionReport: (missionId: string, report: string) => void
  updateMissionStats: (missionId: string, stats: Mission['stats']) => void
  setActiveMission: (missionId: string) => void
  setActiveTab: (tab: 'plan' | 'notes' | 'draft' | 'agents') => void
  fetchMissionStatus: (missionId: string) => Promise<void>
  fetchMissionPlan: (missionId: string) => Promise<void>
  fetchMissionReport: (missionId: string) => Promise<void>
  fetchMissionStats: (missionId: string) => Promise<void>
  fetchMissionNotes: (missionId: string) => Promise<void>
  fetchMissionLogs: (missionId: string) => Promise<void>
  fetchMissionDraft: (missionId: string) => Promise<void>
  ensureMissionInStore: (missionId: string) => Promise<void>
  clearMissions: () => void
  clearActiveMission: () => void
  updateMissionContext: (missionId: string, context: Partial<MissionContext>) => void
  fetchMissionContext: (missionId: string) => Promise<void>
  loadMissionsFromDB: () => Promise<void>
  saveMissionToDB: (mission: Mission) => Promise<void>
}

// Helper to persist mission data to IndexedDB
const persistMissionData = async (mission: Mission) => {
  try {
    // Store mission with all data including stats, plan, draft, report
    await missionDB.storeMission({
      ...mission,
      // Ensure all fields are included
      plan: mission.plan || undefined,
      draft: mission.draft || undefined,
      report: mission.report || undefined,
      stats: mission.stats || undefined
    })
    
    if (mission.notes && mission.notes.length > 0) {
      // Validate notes before storing
      const validatedNotes = mission.notes.map((note, index) => ({
        ...note,
        note_id: note.note_id || `${mission.id}_note_${Date.now()}_${index}`,
        content: note.content || '',
        timestamp: note.timestamp instanceof Date ? note.timestamp : new Date(note.timestamp || Date.now()),
        source: note.source || undefined,
        url: note.url || undefined,
        tags: note.tags || undefined
      }))
      
      await missionDB.storeNotes(mission.id, validatedNotes)
    }
  } catch (error) {
    console.error('Failed to persist mission data:', error)
    // Don't throw the error to prevent UI disruption
  }
}

// Helper to load mission data from IndexedDB
const loadMissionData = async (missionId: string): Promise<Mission | null> => {
  try {
    const mission = await missionDB.getMission(missionId)
    if (!mission) return null
    
    const notes = await missionDB.getNotes(missionId)
    const logs = await missionDB.getLogs(missionId)
    
    return {
      ...mission,
      notes: notes.map(n => ({ ...n, timestamp: ensureDate(n.timestamp) })),
      logs: logs.map(l => ({ ...l, timestamp: ensureDate(l.timestamp) })),
      createdAt: ensureDate(mission.createdAt),
      updatedAt: ensureDate(mission.updatedAt)
    }
  } catch (error) {
    console.error('Failed to load mission data:', error)
    return null
  }
}

export const useMissionStore = create<MissionState>((set, get) => ({
  missions: [],
  activeMission: null,
  missionLogs: {},
  missionContexts: {},
  activeTab: 'plan' as const,
  isLoaded: false,

  setActiveTab: (tab: 'plan' | 'notes' | 'draft' | 'agents') => {
    set({ activeTab: tab })
    
    // Store active tab in localStorage (small data)
    try {
      localStorage.setItem('mission-active-tab', tab)
    } catch (error) {
      console.warn('Failed to save active tab:', error)
    }
  },

  loadMissionsFromDB: async () => {
    try {
      const missions = await missionDB.getAllMissions()
      const loadedMissions: Mission[] = []
      const restoredLogs: { [missionId: string]: Log[] } = {}
      
      for (const mission of missions) {
        const fullMission = await loadMissionData(mission.id)
        if (fullMission) {
          loadedMissions.push(fullMission)
          
          // Restore logs to the missionLogs state
          if (fullMission.logs && fullMission.logs.length > 0) {
            restoredLogs[fullMission.id] = fullMission.logs
          }
        }
      }
      
      // Sort by updated date
      loadedMissions.sort((a, b) => 
        new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      )
      
      set({ 
        missions: loadedMissions, 
        missionLogs: restoredLogs,
        isLoaded: true 
      })
      
      // Restore active tab from localStorage
      try {
        const savedTab = localStorage.getItem('mission-active-tab')
        if (savedTab && ['plan', 'notes', 'draft', 'agents'].includes(savedTab)) {
          set({ activeTab: savedTab as any })
        }
      } catch (error) {
        console.warn('Failed to restore active tab:', error)
      }
      
    } catch (error) {
      console.error('Failed to load missions from DB:', error)
      set({ isLoaded: true })
    }
  },

  saveMissionToDB: async (mission: Mission) => {
    await persistMissionData(mission)
  },

  createMission: async (request: string, options?: { useWebSearch?: boolean; documentGroupId?: string; chatId?: string }) => {
    try {
      const requestBody = {
        request,
        chat_id: options?.chatId || 'default',
        use_web_search: options?.useWebSearch ?? true,
        document_group_id: options?.documentGroupId || null
      }

      const response = await apiClient.post('/api/missions', requestBody)
      const { mission_id, status, created_at, user_request } = response.data

      const newMission: Mission = {
        id: mission_id,
        request: user_request,
        status: status,
        createdAt: new Date(created_at),
        updatedAt: new Date(created_at),
      }

      // Save to IndexedDB
      await persistMissionData(newMission)

      set((state) => ({
        missions: [newMission, ...state.missions],
        activeMission: newMission,
      }))

      return newMission
    } catch (error) {
      console.error('Failed to create mission:', error)
      throw error
    }
  },

  startMission: async (missionId: string) => {
    try {
      await apiClient.post(`/api/missions/${missionId}/start`)
      
      set((state) => {
        const updatedMissions = state.missions.map((mission) =>
          mission.id === missionId
            ? { ...mission, status: 'running' as const, updatedAt: new Date() }
            : mission
        )

        const activeMission = state.activeMission?.id === missionId
          ? updatedMissions.find(m => m.id === missionId) || null
          : state.activeMission

        // Save updated mission to IndexedDB
        const updatedMission = updatedMissions.find(m => m.id === missionId)
        if (updatedMission) {
          persistMissionData(updatedMission)
        }

        return {
          missions: updatedMissions,
          activeMission,
        }
      })
    } catch (error) {
      console.error('Failed to start mission:', error)
      throw error
    }
  },

  stopMission: async (missionId: string) => {
    try {
      await apiClient.post(`/api/missions/${missionId}/stop`)
      
      set((state) => {
        const updatedMissions = state.missions.map((mission) =>
          mission.id === missionId
            ? { ...mission, status: 'stopped' as const, updatedAt: new Date() }
            : mission
        )

        const activeMission = state.activeMission?.id === missionId
          ? updatedMissions.find(m => m.id === missionId) || null
          : state.activeMission

        // Save updated mission to IndexedDB
        const updatedMission = updatedMissions.find(m => m.id === missionId)
        if (updatedMission) {
          persistMissionData(updatedMission)
        }

        return {
          missions: updatedMissions,
          activeMission,
        }
      })
    } catch (error) {
      console.error('Failed to stop mission:', error)
      throw error
    }
  },

  resumeMission: async (missionId: string) => {
    try {
      await apiClient.post(`/api/missions/${missionId}/resume`)
      
      set((state) => {
        const updatedMissions = state.missions.map((mission) =>
          mission.id === missionId
            ? { ...mission, status: 'running' as const, updatedAt: new Date() }
            : mission
        )

        const activeMission = state.activeMission?.id === missionId
          ? updatedMissions.find(m => m.id === missionId) || null
          : state.activeMission

        // Save updated mission to IndexedDB
        const updatedMission = updatedMissions.find(m => m.id === missionId)
        if (updatedMission) {
          persistMissionData(updatedMission)
        }

        return {
          missions: updatedMissions,
          activeMission,
        }
      })
    } catch (error) {
      console.error('Failed to resume mission:', error)
      throw error
    }
  },

  updateMissionStatus: (missionId: string, status: Mission['status']) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { ...mission, status, updatedAt: new Date() }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  setMissionPlan: (missionId: string, plan: string) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { ...mission, plan, updatedAt: new Date() }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  setMissionNotes: (missionId: string, notes: Note[]) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { 
              ...mission, 
              notes: notes.map((n, index) => ({ 
                ...n, 
                note_id: n.note_id || `${missionId}_note_${Date.now()}_${index}`,
                content: n.content || '',
                timestamp: ensureDate(n.timestamp || new Date()),
                source: n.source || undefined,
                url: n.url || undefined,
                tags: n.tags || undefined
              })), 
              updatedAt: new Date() 
            }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  appendMissionNotes: (missionId: string, newNotes: Note[]) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) => {
        if (mission.id === missionId) {
          const existingNotes = mission.notes || []
          const existingNoteIds = new Set(existingNotes.map(note => note.note_id))
          
          // Validate and fix new notes before processing
          const validatedNewNotes = newNotes.map((note, index) => ({
            ...note,
            note_id: note.note_id || `${missionId}_note_${Date.now()}_${index}`,
            content: note.content || '',
            timestamp: ensureDate(note.timestamp || new Date()),
            source: note.source || undefined,
            url: note.url || undefined,
            tags: note.tags || undefined
          }))
          
          // Only add notes that don't already exist (deduplication)
          const uniqueNewNotes = validatedNewNotes.filter(note => !existingNoteIds.has(note.note_id))
          
          const updatedMission = {
            ...mission,
            notes: [
              ...existingNotes, 
              ...uniqueNewNotes
            ],
            updatedAt: new Date()
          }

          // Save updated mission to IndexedDB
          persistMissionData(updatedMission)

          return updatedMission
        }
        return mission
      })

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  setMissionLogs: async (missionId: string, logs: Log[]) => {
    const processedLogs = logs.map(l => ({ ...l, timestamp: ensureDate(l.timestamp) }))
    
    // Store logs in IndexedDB
    try {
      await missionDB.storeLogs(missionId, processedLogs)
    } catch (error) {
      console.error('Failed to store logs in IndexedDB:', error)
    }
    
    set((state) => ({
      missionLogs: {
        ...state.missionLogs,
        [missionId]: processedLogs,
      },
    }))
  },

  setMissionDraft: (missionId: string, draft: string) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { ...mission, draft, updatedAt: new Date() }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  updateMissionReport: (missionId: string, report: string) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { ...mission, report, updatedAt: new Date() }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  updateMissionStats: (missionId: string, stats: Mission['stats']) => {
    set((state) => {
      const updatedMissions = state.missions.map((mission) =>
        mission.id === missionId
          ? { ...mission, stats, updatedAt: new Date() }
          : mission
      )

      const activeMission = state.activeMission?.id === missionId
        ? updatedMissions.find(m => m.id === missionId) || null
        : state.activeMission

      // Save updated mission to IndexedDB
      const updatedMission = updatedMissions.find(m => m.id === missionId)
      if (updatedMission) {
        persistMissionData(updatedMission)
      }

      return {
        missions: updatedMissions,
        activeMission,
      }
    })
  },

  setActiveMission: (missionId: string) => {
    const mission = get().missions.find((m) => m.id === missionId)
    if (mission) {
      set({ activeMission: mission })
    }
  },

  fetchMissionStatus: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/status`)
      const { status, updated_at } = response.data
      
      set((state) => {
        const updatedMissions = state.missions.map((mission) =>
          mission.id === missionId
            ? { 
                ...mission, 
                status: status,
                updatedAt: new Date(updated_at)
              }
            : mission
        )

        const activeMission = state.activeMission?.id === missionId
          ? updatedMissions.find(m => m.id === missionId) || null
          : state.activeMission

        // Save updated mission to IndexedDB
        const updatedMission = updatedMissions.find(m => m.id === missionId)
        if (updatedMission) {
          persistMissionData(updatedMission)
        }

        return {
          missions: updatedMissions,
          activeMission,
        }
      })
    } catch (error) {
      console.error('Failed to fetch mission status:', error)
    }
  },

  fetchMissionPlan: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/plan`)
      const { plan } = response.data
      
      // Convert plan object to string if it exists
      const planString = plan ? (typeof plan === 'string' ? plan : JSON.stringify(plan, null, 2)) : ''
      if (planString) {
        get().setMissionPlan(missionId, planString)
      }
    } catch (error) {
      console.error('Failed to fetch mission plan:', error)
    }
  },

  fetchMissionReport: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/report`)
      const { final_report } = response.data
      get().updateMissionReport(missionId, final_report)
    } catch (error) {
      console.error('Failed to fetch mission report:', error)
    }
  },

  fetchMissionStats: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/stats`)
      const { total_cost, total_prompt_tokens, total_completion_tokens, total_web_search_calls } = response.data
      
      const stats = {
        total_cost,
        total_tokens: total_prompt_tokens + total_completion_tokens,
        tool_usage: {
          web_search: total_web_search_calls
        }
      }
      
      get().updateMissionStats(missionId, stats)
    } catch (error) {
      console.error('Failed to fetch mission stats:', error)
    }
  },

  fetchMissionNotes: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/notes?limit=50&offset=0`)
      if (response.data) {
        // Handle both old and new API format
        const notes = response.data.notes || response.data
        get().setMissionNotes(missionId, notes)
      }
    } catch (error) {
      console.error('Failed to fetch mission notes:', error)
    }
  },

  fetchMissionLogs: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/logs`)
      if (response.data && response.data.logs) {
        get().setMissionLogs(missionId, response.data.logs)
      }
    } catch (error) {
      console.error('Failed to fetch mission logs:', error)
    }
  },

  fetchMissionDraft: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/draft`)
      if (response.data && response.data.draft) {
        get().setMissionDraft(missionId, response.data.draft)
      }
    } catch (error) {
      console.error('Failed to fetch mission draft:', error)
    }
  },

  ensureMissionInStore: async (missionId: string) => {
    try {
      // Check if mission already exists in store
      const existingMission = get().missions.find(m => m.id === missionId)
      if (existingMission) {
        // Set as active mission but DON'T fetch additional data to prevent loops
        get().setActiveMission(missionId)
        return
      }

      // Try to load from IndexedDB first
      const missionFromDB = await loadMissionData(missionId)
      if (missionFromDB) {
        set((state) => ({
          missions: [missionFromDB, ...state.missions],
          activeMission: missionFromDB,
        }))
        return
      }

      // If mission doesn't exist in DB, fetch it from the backend
      const response = await apiClient.get(`/api/missions/${missionId}/status`)
      const { status, updated_at } = response.data

      // Create a basic mission object
      const mission: Mission = {
        id: missionId,
        request: 'Loading...', // We'll need to fetch this separately if needed
        status: status,
        createdAt: new Date(updated_at),
        updatedAt: new Date(updated_at),
      }

      // Save to IndexedDB and add to store
      await persistMissionData(mission)
      
      set((state) => ({
        missions: [mission, ...state.missions],
        activeMission: mission,
      }))

      // DON'T fetch additional mission data here to prevent infinite loops
      // Data will be loaded on-demand when user navigates to specific tabs
    } catch (error) {
      console.error('Failed to ensure mission in store:', error)
    }
  },

  clearMissions: () => {
    set({
      missions: [],
      activeMission: null,
    })
  },

  clearActiveMission: () => {
    set({ activeMission: null })
  },

  updateMissionContext: (missionId: string, context: Partial<MissionContext>) => {
    set((state) => ({
      missionContexts: {
        ...state.missionContexts,
        [missionId]: {
          ...state.missionContexts[missionId],
          ...context,
        },
      },
    }))
  },

  fetchMissionContext: async (missionId: string) => {
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/context`)
      if (response.data) {
        get().updateMissionContext(missionId, response.data)
      }
    } catch (error) {
      console.error('Failed to fetch mission context:', error)
    }
  },
}))

// Initialize the store by loading missions from IndexedDB
const initializeStore = async () => {
  try {
    const store = useMissionStore.getState()
    if (!store.isLoaded) {
      await store.loadMissionsFromDB()
    }
  } catch (error) {
    console.error('Failed to initialize mission store:', error)
  }
}

// Auto-initialize when the module loads
initializeStore()
