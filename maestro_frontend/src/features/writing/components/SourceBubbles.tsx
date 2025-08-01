import React from 'react'
import { ExternalLink, FileText } from 'lucide-react'
import type { Source } from '../api'

interface SourceBubblesProps {
  sources: Source[]
}

export const SourceBubbles: React.FC<SourceBubblesProps> = ({ sources }) => {
  if (!sources || sources.length === 0) {
    return null
  }

  const handleWebSourceClick = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {sources.map((source, index) => {
        const isWebSource = source.type === 'web'
        
        return (
          <div
            key={index}
            className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ${
              isWebSource
                ? 'bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer'
                : 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
            }`}
            onClick={isWebSource ? () => handleWebSourceClick((source as any).url) : undefined}
            title={source.title}
          >
            {/* Icon */}
            <div className="mr-1.5">
              {isWebSource ? (
                <ExternalLink className="h-3 w-3" />
              ) : (
                <FileText className="h-3 w-3" />
              )}
            </div>
            
            {/* Title */}
            <span className="truncate max-w-[120px]">
              {source.title}
            </span>
          </div>
        )
      })}
    </div>
  )
}
