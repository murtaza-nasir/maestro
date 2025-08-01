import React from 'react'

interface PanelHeaderProps {
  title: string
  subtitle?: React.ReactNode
  icon?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export const PanelHeader: React.FC<PanelHeaderProps> = ({
  title,
  subtitle,
  icon,
  actions,
  className = ''
}) => {
  return (
    <div className={`bg-header-background border-b border-border px-6 py-4 min-h-[88px] ${className}`}>
      <div className="flex items-start justify-between h-full">
        <div className="flex-1 min-w-0">
          <div className="flex items-start space-x-3">
            {icon && (
              <div className="flex-shrink-0 mt-0.5">
                {icon}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold text-foreground truncate">
                {title}
              </h2>
              {subtitle && (
                <div className="text-sm text-muted-foreground mt-0.5">
                  {subtitle}
                </div>
              )}
            </div>
          </div>
        </div>
        {actions && (
          <div className="flex-shrink-0 ml-4">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
