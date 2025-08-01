import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../features/auth/store'
import { useDocumentContext } from '../../features/documents/context/DocumentContext'
import { ChatHistorySidebar } from '../../features/chat/components'
import { DocumentGroupSidebar } from '../../features/documents/components/DocumentGroupSidebar'
import { WritingChatSidebar } from '../../features/writing/components/WritingChatSidebar'
import { Button } from '../ui/button'
import { ViewToggle } from '../ui/ViewToggle'
import { useViewStore } from '../../stores/viewStore'
import { 
  Menu,
  X,
  Settings,
  LogOut
} from 'lucide-react'
import { useDocumentUploadManager } from '../../features/documents/context/DocumentUploadContext'
import { UploadProgressToast } from '../../features/documents/components/UploadProgressToast'
import { SettingsDialog } from '../../features/auth/components/SettingsDialog'
import { useTheme } from '../../contexts/ThemeContext'

export const MainLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { user, logout } = useAuthStore()
  const { setSelectedGroup } = useDocumentContext()
  const { uploadingFiles, cancelUpload, cancelAllUploads, clearCompletedUploads, dismissFile } = useDocumentUploadManager()
  const { currentView, setView } = useViewStore()
  const { theme, getThemeClasses } = useTheme()
  const navigate = useNavigate()
  
  // Refs to preserve scroll positions for each sidebar view
  const sidebarScrollPositions = useRef<Record<string, number>>({
    research: 0,
    documents: 0
  })
  const sidebarContentRef = useRef<HTMLDivElement>(null)
  
  // Save scroll position when view changes
  const saveScrollPosition = () => {
    if (sidebarContentRef.current) {
      const scrollableElement = sidebarContentRef.current.querySelector('.flex-1.overflow-y-auto')
      if (scrollableElement) {
        sidebarScrollPositions.current[currentView] = scrollableElement.scrollTop
      }
    }
  }
  
  // Restore scroll position after view change
  const restoreScrollPosition = () => {
    if (sidebarContentRef.current) {
      const scrollableElement = sidebarContentRef.current.querySelector('.flex-1.overflow-y-auto')
      if (scrollableElement) {
        const savedPosition = sidebarScrollPositions.current[currentView] || 0
        scrollableElement.scrollTop = savedPosition
      }
    }
  }
  
  // Save scroll position before view changes
  useEffect(() => {
    return () => {
      saveScrollPosition()
    }
  }, [currentView])
  
  // Restore scroll position after view changes
  useEffect(() => {
    const timer = setTimeout(() => {
      restoreScrollPosition()
    }, 0)
    return () => clearTimeout(timer)
  }, [currentView])

  const handleLogout = async () => {
    try {
      await logout()
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen)
  }

  const handleNavigateHome = () => {
    navigate('/dashboard')
  }

  const handleSelectGroup = useCallback((group: any) => {
    // Save current scroll position before changing view
    saveScrollPosition()
    setSelectedGroup(group);
    setView('documents');
    navigate('/app');
    // Keep sidebar open when selecting groups
  }, [setSelectedGroup, setView, navigate, saveScrollPosition]);
  
  const handleViewChange = useCallback((view: any) => {
    // Save current scroll position before changing view
    saveScrollPosition()
    setView(view)
  }, [setView])

  const SidebarContent = useMemo(() => {
    switch (currentView) {
      case 'research':
        return <ChatHistorySidebar />;
      case 'documents':
        return <DocumentGroupSidebar onSelectGroup={handleSelectGroup} />;
      case 'writing':
        return <WritingChatSidebar />;
      default:
        return null;
    }
  }, [currentView, handleSelectGroup])

  return (
    <div className={`flex flex-col h-screen bg-background text-foreground ${getThemeClasses()}`}>
      {/* Top Header - Compact & Polished */}
      <header className="bg-card/95 backdrop-blur-sm shadow-sm border-b border-border/50 px-4 py-2.5 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleSidebar}
              className="p-1.5 text-foreground hover:bg-accent/80 transition-colors rounded-md"
            >
              {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>
            
            <div 
              className="flex items-center space-x-2.5 cursor-pointer group transition-all duration-200 hover:opacity-80"
              onClick={handleNavigateHome}
            >
              <div className="relative">
                <img 
                  src={theme === 'dark' ? '/icon_dark.png' : '/icon_original.png'} 
                  alt="MAESTRO Logo" 
                  className="h-7 w-7 transition-transform group-hover:scale-105"
                />
              </div>
              <div className="flex items-baseline space-x-2">
                <h1 className="text-xl font-semibold text-foreground tracking-tight">MAESTRO</h1>
                <span className="text-xs text-muted-foreground/80 hidden md:inline font-medium">
                  AI Research Assistant
                </span>
              </div>
            </div>
          </div>

          {/* Header Actions */}
          <div className="flex items-center gap-3">
            <ViewToggle
              currentView={currentView}
              onViewChange={handleViewChange}
            />
          </div>
        </div>
      </header>

      {/* Content Area with Sidebar */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className={`${
          sidebarOpen ? 'w-80' : 'w-0'
        } transition-all duration-300 ease-in-out overflow-hidden bg-card shadow-lg flex flex-col border-r border-border`}>
          {/* Sidebar Content */}
          <div ref={sidebarContentRef} className="flex-1 overflow-y-auto">
            {SidebarContent}
          </div>

          {/* Sidebar Footer */}
          <div className="p-4 border-t border-border">
            <div className="flex items-center space-x-3 mb-3">
              <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center">
                <span className="text-primary-foreground text-sm font-medium">
                  {user?.username?.charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-foreground truncate">
                  {user?.username}
                </div>
              </div>
            </div>
            
            <div className="flex space-x-2">
              <Button variant="ghost" size="sm" className="flex-1 text-foreground hover:bg-accent" onClick={() => setSettingsOpen(true)}>
                <Settings className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" className="flex-1 text-foreground hover:bg-accent" onClick={handleLogout}>
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto bg-background">
          <Outlet />
        </main>
      </div>
      
        <UploadProgressToast
          uploadingFiles={uploadingFiles}
          onCancelAll={cancelAllUploads}
          onCancelUpload={cancelUpload}
          onClearCompleted={clearCompletedUploads}
          onDismissFile={dismissFile}
        />
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  )
}
