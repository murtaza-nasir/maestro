import React, { useState } from 'react'
import { Button } from '../../../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { Switch } from '../../../components/ui/switch'
import { Label } from '../../../components/ui/label'
import { Plus, FolderOpen, Globe } from 'lucide-react'

export const WritingSessionControls: React.FC = () => {
  const [selectedDocumentGroup, setSelectedDocumentGroup] = useState<string>('')
  const [webSearchEnabled, setWebSearchEnabled] = useState(false)

  // TODO: Replace with actual document groups from API
  const documentGroups = [
    { id: '1', name: 'Research Project Alpha' },
    { id: '2', name: 'Literature Review' },
    { id: '3', name: 'Methodology Study' },
  ]

  const handleCreateNewSession = () => {
    // TODO: Implement create new writing session
    console.log('Creating new writing session...')
  }

  return (
    <div className="space-y-4">
      {/* Document Group Selection */}
      <div className="space-y-2">
        <Label htmlFor="document-group" className="text-sm font-medium">
          Document Group
        </Label>
        <div className="flex space-x-2">
          <Select value={selectedDocumentGroup} onValueChange={setSelectedDocumentGroup}>
            <SelectTrigger className="flex-1">
              <SelectValue placeholder="Select a document group..." />
            </SelectTrigger>
            <SelectContent>
              {documentGroups.map((group) => (
                <SelectItem key={group.id} value={group.id}>
                  <div className="flex items-center">
                    <FolderOpen className="h-4 w-4 mr-2" />
                    {group.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button 
            variant="outline" 
            size="sm"
            onClick={handleCreateNewSession}
            className="px-3"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Web Search Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Globe className="h-4 w-4 text-text-secondary" />
          <Label htmlFor="web-search" className="text-sm font-medium">
            Enable Web Search
          </Label>
        </div>
        <Switch
          id="web-search"
          checked={webSearchEnabled}
          onCheckedChange={setWebSearchEnabled}
        />
      </div>

      {/* Session Info */}
      {selectedDocumentGroup && (
        <div className="p-3 bg-primary/10 rounded-lg border border-primary/20">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-primary">
                Active Writing Session
              </p>
              <p className="text-xs text-primary/80">
                {documentGroups.find(g => g.id === selectedDocumentGroup)?.name}
              </p>
            </div>
            <div className="text-xs text-primary/90">
              {webSearchEnabled ? 'Web search enabled' : 'Local documents only'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
