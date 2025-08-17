import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ViewMode = 'research' | 'writing' | 'documents'

interface ViewState {
  currentView: ViewMode
  setView: (view: ViewMode) => void
}

// @ts-ignore - Zustand TypeScript compatibility issues
export const useViewStore = create<ViewState>()(
  // @ts-ignore
  persist(
    (set) => ({
      currentView: 'research',
      setView: (view: ViewMode) => set({ currentView: view }),
    }),
    {
      name: 'maestro-view-storage',
    }
  )
)