import React, { useState, useRef, useEffect } from 'react'

interface SplitPaneLayoutProps {
  leftPanel: React.ReactNode
  rightPanel: React.ReactNode
  defaultLeftWidth?: number // percentage (0-100)
  minLeftWidth?: number // percentage
  maxLeftWidth?: number // percentage
  showRightPanel?: boolean
}

interface PanelControlsContextType {
  toggleRightPanel: () => void
  toggleLeftPanel: () => void
  maximizeLeft: () => void
  maximizeRight: () => void
  resetLayout: () => void
  isRightPanelCollapsed: boolean
  isLeftPanelCollapsed: boolean
  isLeftMaximized: boolean
  isRightMaximized: boolean
}

export const PanelControlsContext = React.createContext<PanelControlsContextType | null>(null)

export const usePanelControls = () => {
  const context = React.useContext(PanelControlsContext)
  if (!context) {
    throw new Error('usePanelControls must be used within a SplitPaneLayout')
  }
  return context
}

export const SplitPaneLayout: React.FC<SplitPaneLayoutProps> = ({
  leftPanel,
  rightPanel,
  defaultLeftWidth = 50,
  minLeftWidth = 20,
  maxLeftWidth = 80,
  showRightPanel = true
}) => {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth)
  const [isResizing, setIsResizing] = useState(false)
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(!showRightPanel)
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Panel control functions
  const toggleRightPanel = () => {
    setIsRightPanelCollapsed(!isRightPanelCollapsed)
  }

  const toggleLeftPanel = () => {
    setIsLeftPanelCollapsed(!isLeftPanelCollapsed)
  }

  const maximizeLeft = () => {
    setIsRightPanelCollapsed(true)
    setIsLeftPanelCollapsed(false)
  }

  const maximizeRight = () => {
    setLeftWidth(20) // Minimize left panel
    setIsRightPanelCollapsed(false)
    setIsLeftPanelCollapsed(false)
  }

  const resetLayout = () => {
    setLeftWidth(defaultLeftWidth)
    setIsRightPanelCollapsed(false)
    setIsLeftPanelCollapsed(false)
  }

  // Determine panel states
  const isLeftMaximized = isRightPanelCollapsed && !isLeftPanelCollapsed
  const isRightMaximized = leftWidth <= 25 && !isRightPanelCollapsed && !isLeftPanelCollapsed

  const panelControlsValue: PanelControlsContextType = {
    toggleRightPanel,
    toggleLeftPanel,
    maximizeLeft,
    maximizeRight,
    resetLayout,
    isRightPanelCollapsed,
    isLeftPanelCollapsed,
    isLeftMaximized,
    isRightMaximized
  }

  // Handle mouse move during resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !containerRef.current) return

      const containerRect = containerRef.current.getBoundingClientRect()
      const newLeftWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100
      
      // Clamp the width between min and max
      const clampedWidth = Math.max(minLeftWidth, Math.min(maxLeftWidth, newLeftWidth))
      setLeftWidth(clampedWidth)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, minLeftWidth, maxLeftWidth])

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }


  // Calculate effective widths based on panel states
  let effectiveLeftWidth = 0
  let effectiveRightWidth = 0

  if (isLeftPanelCollapsed && isRightPanelCollapsed) {
    // Both collapsed - show nothing (shouldn't happen in practice)
    effectiveLeftWidth = 0
    effectiveRightWidth = 0
  } else if (isLeftPanelCollapsed) {
    // Left collapsed, right takes full width
    effectiveLeftWidth = 0
    effectiveRightWidth = 100
  } else if (isRightPanelCollapsed) {
    // Right collapsed, left takes full width
    effectiveLeftWidth = 100
    effectiveRightWidth = 0
  } else {
    // Both visible, use normal split
    effectiveLeftWidth = leftWidth
    effectiveRightWidth = 100 - leftWidth
  }

  return (
    <PanelControlsContext.Provider value={panelControlsValue}>
      <div ref={containerRef} className="h-full flex relative bg-background">
        {/* Left Panel */}
        {!isLeftPanelCollapsed && (
          <div 
            className="flex flex-col bg-background border-r border-border relative"
            style={{ width: `${effectiveLeftWidth}%` }}
          >
            {/* Left Panel Content */}
            <div className="flex-1 overflow-hidden">
              {leftPanel}
            </div>
          </div>
        )}

        {/* Resize Handle */}
        {!isRightPanelCollapsed && !isLeftPanelCollapsed && (
          <div
            className="w-1 bg-border hover:bg-primary cursor-col-resize transition-colors duration-150 relative group"
            onMouseDown={handleResizeStart}
          >
            <div className="absolute inset-y-0 -left-1 -right-1 group-hover:bg-primary/20" />
          </div>
        )}

        {/* Right Panel */}
        {!isRightPanelCollapsed && (
          <div 
            className="flex flex-col bg-background relative"
            style={{ width: `${effectiveRightWidth}%` }}
          >
            {/* Right Panel Content */}
            <div className="flex-1 overflow-hidden">
              {rightPanel}
            </div>
          </div>
        )}
      </div>
    </PanelControlsContext.Provider>
  )
}
