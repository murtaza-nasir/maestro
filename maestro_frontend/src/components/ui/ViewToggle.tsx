import React from 'react'
import { Button } from './button'
import { MessageSquare, PenTool, FileText } from 'lucide-react'

export type ViewMode = 'research' | 'writing' | 'documents'

interface ViewToggleProps {
  currentView: ViewMode
  onViewChange: (view: ViewMode) => void
  className?: string
}

export const ViewToggle: React.FC<ViewToggleProps> = ({
  currentView,
  onViewChange,
  className = ''
}) => {
  const views = [
    { key: 'research', icon: MessageSquare, label: 'Research' },
    { key: 'writing', icon: PenTool, label: 'Writing' },
    { key: 'documents', icon: FileText, label: 'Documents' }
  ] as const

  return (
    <div className={`flex bg-muted/60 backdrop-blur-sm rounded-lg p-0.5 border border-border/50 ${className}`}>
      {views.map(({ key, icon: Icon, label }) => (
        <Button
          key={key}
          variant="ghost"
          size="sm"
          onClick={() => onViewChange(key)}
          className={`px-2.5 py-1.5 h-8 text-xs font-medium rounded-md transition-all duration-200 ${
            currentView === key
              ? 'bg-background text-foreground shadow-sm border border-border/50'
              : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
          }`}
        >
          <Icon className="h-3.5 w-3.5 mr-1.5" />
          <span className="hidden sm:inline">{label}</span>
        </Button>
      ))}
    </div>
  )
}
