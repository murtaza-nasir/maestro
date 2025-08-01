import React from 'react'
import { Button } from './button'
import { Eye, EyeOff } from 'lucide-react'

interface PanelControlsProps {
  onTogglePanel?: () => void
  isCollapsed?: boolean
  showToggle?: boolean
  toggleTooltip?: string
}

export const PanelControls: React.FC<PanelControlsProps> = ({
  onTogglePanel,
  isCollapsed = false,
  showToggle = true,
}) => {
  return (
    <div className="flex items-center space-x-1">
      {/* Show/Hide Panel Button - Keep only this one */}
      {showToggle && onTogglePanel && (
        <Button
          onClick={onTogglePanel}
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 hover:bg-gray-100"
          title={isCollapsed ? "Show Panel" : "Hide Panel"}
        >
          {isCollapsed ? (
            <Eye className="h-4 w-4" />
          ) : (
            <EyeOff className="h-4 w-4" />
          )}
        </Button>
      )}
    </div>
  )
}
