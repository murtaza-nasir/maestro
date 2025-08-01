import React from 'react'
import { Button } from './button'
import { Edit2, Trash2 } from 'lucide-react'

interface ListItemAction {
  icon: React.ReactNode
  label: string
  onClick: (e: React.MouseEvent) => void
  variant?: 'default' | 'destructive'
  className?: string
}

interface ListItemProps {
  /** Whether this item is currently selected/active */
  isSelected?: boolean
  /** Click handler for the main item */
  onClick?: () => void
  /** Main icon to display */
  icon?: React.ReactNode
  /** Primary title text */
  title: string
  /** Secondary subtitle text */
  subtitle?: string
  /** Timestamp or date text */
  timestamp?: string
  /** Additional metadata items to display */
  metadata?: Array<{
    icon?: React.ReactNode
    text: string
  }>
  /** Action buttons (edit, delete, etc.) */
  actions?: ListItemAction[]
  /** Additional content to render below the main content */
  children?: React.ReactNode
  /** Custom className for the container */
  className?: string
  /** Whether to show actions permanently (not just on hover) */
  showActionsPermanently?: boolean
}

export const ListItem: React.FC<ListItemProps> = ({
  isSelected = false,
  onClick,
  icon,
  title,
  subtitle,
  timestamp,
  metadata = [],
  actions = [],
  children,
  className = '',
  showActionsPermanently = false
}) => {
  return (
    <div
      className={`group relative p-2 rounded-md cursor-pointer transition-all duration-200 ${
        isSelected
          ? 'bg-primary/5 border border-primary/20 shadow-sm'
          : 'bg-background border border-border/50 hover:bg-muted/50 hover:border-border'
      } ${className}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-2">
        {/* Icon */}
        {icon && (
          <div className="flex-shrink-0 mt-0.5">
            <div className={`${isSelected ? 'text-primary' : 'text-muted-foreground'}`}>
              {icon}
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title Row */}
          <div className="flex items-start justify-between mb-0.5">
            <h3 className={`font-medium text-xs leading-tight ${
              isSelected ? 'text-primary' : 'text-foreground'
            }`} title={title}>
              {title}
            </h3>
          </div>

          {/* Subtitle */}
          {subtitle && (
            <p className="text-xs text-muted-foreground mb-0.5 line-clamp-1" title={subtitle}>
              {subtitle}
            </p>
          )}

          {/* Metadata */}
          {metadata.length > 0 && (
            <div className="space-y-0.5 mb-0.5">
              {metadata.map((item, index) => (
                <div key={index} className="flex items-center gap-1 text-xs text-muted-foreground">
                  {item.icon && <span className="flex-shrink-0">{item.icon}</span>}
                  <span className="truncate">{item.text}</span>
                </div>
              ))}
            </div>
          )}

          {/* Bottom Row: Timestamp and Actions */}
          <div className="flex items-center justify-between">
            {/* Timestamp */}
            {timestamp && (
              <span className="text-xs text-muted-foreground">
                {timestamp}
              </span>
            )}

            {/* Actions */}
            {actions.length > 0 && (
              <div className={`flex items-center gap-0.5 ml-auto ${
                showActionsPermanently 
                  ? 'opacity-100' 
                  : `opacity-0 group-hover:opacity-100 transition-opacity ${isSelected ? 'opacity-100' : ''}`
              }`}>
                {actions.map((action, index) => (
                  <Button
                    key={index}
                    variant="ghost"
                    size="sm"
                    className={`h-5 w-5 p-0 ${
                      action.variant === 'destructive' 
                        ? 'text-destructive hover:text-destructive/80 hover:bg-destructive/10' 
                        : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                    } ${action.className || ''}`}
                    onClick={action.onClick}
                    title={action.label}
                  >
                    {action.icon}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Additional Content */}
          {children}
        </div>
      </div>
    </div>
  )
}

// Convenience components for common action types
export const createEditAction = (onClick: (e: React.MouseEvent) => void): ListItemAction => ({
  icon: <Edit2 className="h-3 w-3" />,
  label: 'Edit',
  onClick
})

export const createDeleteAction = (onClick: (e: React.MouseEvent) => void): ListItemAction => ({
  icon: <Trash2 className="h-3 w-3" />,
  label: 'Delete',
  onClick,
  variant: 'destructive'
})
