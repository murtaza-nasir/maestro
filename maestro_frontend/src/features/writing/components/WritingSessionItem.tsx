import React from 'react'
import { 
  FileText, 
  Database,
  Globe
} from 'lucide-react'
import { ListItem, createDeleteAction } from '../../../components/ui/ListItem'
import type { WritingSession } from '../api'
import type { DocumentGroupWithCount } from '../../documents/types'

interface WritingSessionItemProps {
  session: WritingSession
  isSelected: boolean
  onClick: () => void
  onDelete: () => void
  documentGroups: DocumentGroupWithCount[]
}

export const WritingSessionItem: React.FC<WritingSessionItemProps> = ({
  session,
  isSelected,
  onClick,
  onDelete,
  documentGroups
}) => {
  const documentGroup = documentGroups.find(group => group.id === session.document_group_id)
  
  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
      
      if (diffDays === 0) {
        return 'Today'
      } else if (diffDays === 1) {
        return 'Yesterday'
      } else if (diffDays < 7) {
        return `${diffDays} days ago`
      } else {
        return date.toLocaleDateString()
      }
    } catch {
      return 'Unknown'
    }
  }

  const metadata = [
    {
      icon: <Database className="h-3 w-3" />,
      text: documentGroup ? `${documentGroup.name} (${documentGroup.document_count})` : 'No documents'
    },
    {
      icon: <Globe className="h-3 w-3" />,
      text: `Web search: ${session.web_search_enabled ? 'Enabled' : 'Disabled'}`
    }
  ]

  const actions = [
    createDeleteAction((e: React.MouseEvent) => {
      e.stopPropagation()
      onDelete()
    })
  ]

  return (
    <ListItem
      isSelected={isSelected}
      onClick={onClick}
      icon={<FileText className="h-4 w-4" />}
      title={session.name}
      timestamp={`Updated ${formatDate(session.updated_at)}`}
      metadata={metadata}
      actions={actions}
      showActionsPermanently={true}
    />
  )
}
