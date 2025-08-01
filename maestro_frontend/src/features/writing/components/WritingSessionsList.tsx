import React, { useState, useEffect } from 'react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent } from '../../../components/ui/card'
import { useToast } from '../../../components/ui/toast'
import { Plus, Search, FileText, Calendar, Folder, Trash2 } from 'lucide-react'
import { useWritingStore } from '../store'
import { getDocumentGroups } from '../../documents/api'
import type { DocumentGroup } from '../../documents/types'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select'

export const WritingSessionsList: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newSessionName, setNewSessionName] = useState('')
  const [selectedDocumentGroup, setSelectedDocumentGroup] = useState<string>('')
  const [webSearchEnabled, setWebSearchEnabled] = useState(true)
  const [documentGroups, setDocumentGroups] = useState<DocumentGroup[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const { addToast } = useToast()

  const {
    sessions,
    currentSession,
    isLoading,
    loadSessions,
    createSession,
    selectSession,
    deleteSession
  } = useWritingStore()

  // Load sessions and document groups on mount
  useEffect(() => {
    loadSessions()
    fetchDocumentGroups()
  }, [loadSessions])

  const fetchDocumentGroups = async () => {
    try {
      const groups = await getDocumentGroups()
      setDocumentGroups(groups)
    } catch (error) {
      console.error('Failed to fetch document groups:', error)
    }
  }

  const handleCreateSession = async () => {
    if (!newSessionName.trim()) {
      addToast({
        type: 'error',
        title: 'Invalid Input',
        message: 'Please enter a session name.',
        duration: 3000
      })
      return
    }

    setIsCreating(true)
    try {
      await createSession({
        name: newSessionName.trim(),
        document_group_id: selectedDocumentGroup || null,
        web_search_enabled: webSearchEnabled
      })

      // Reset form
      setNewSessionName('')
      setSelectedDocumentGroup('')
      setWebSearchEnabled(true)
      setShowCreateForm(false)

      addToast({
        type: 'success',
        title: 'Session Created',
        message: 'Your writing session has been created successfully.',
        duration: 3000
      })
    } catch (error) {
      console.error('Failed to create session:', error)
      addToast({
        type: 'error',
        title: 'Creation Failed',
        message: 'Failed to create writing session. Please try again.',
        duration: 5000
      })
    } finally {
      setIsCreating(false)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId)
      setDeleteConfirm(null)
      addToast({
        type: 'success',
        title: 'Session Deleted',
        message: 'Writing session has been deleted.',
        duration: 3000
      })
    } catch (error) {
      console.error('Failed to delete session:', error)
      addToast({
        type: 'error',
        title: 'Deletion Failed',
        message: 'Failed to delete writing session. Please try again.',
        duration: 5000
      })
    }
  }

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

  // Filter sessions based on search term
  const filteredSessions = sessions.filter(session =>
    session.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary">Writing Sessions</h2>
          <Button
            onClick={() => setShowCreateForm(!showCreateForm)}
            size="sm"
            className="flex items-center"
          >
            <Plus className="h-4 w-4 mr-1" />
            New
          </Button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-text-tertiary" />
          <Input
            placeholder="Search sessions..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 bg-background-alt border-border placeholder:text-text-secondary"
          />
        </div>

        {/* Create Session Form */}
        {showCreateForm && (
          <Card className="mt-4 bg-background-alt border-border">
            <CardContent className="p-4 space-y-4">
              <div>
                <label className="text-sm font-medium text-text-secondary mb-1 block">
                  Session Name
                </label>
                <Input
                  placeholder="Enter session name..."
                  value={newSessionName}
                  onChange={(e) => setNewSessionName(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                      handleCreateSession()
                    }
                  }}
                />
              </div>

              <div>
                <label className="text-sm font-medium text-text-secondary mb-1 block">
                  Document Group (Optional)
                </label>
                <Select
                  value={selectedDocumentGroup}
                  onValueChange={setSelectedDocumentGroup}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a document group..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {documentGroups.map((group) => (
                      <SelectItem key={group.id} value={group.id}>
                        {group.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-text-secondary">
                  Enable Web Search
                </label>
                <button
                  type="button"
                  onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                    webSearchEnabled ? 'bg-primary' : 'bg-muted'
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      webSearchEnabled ? 'translate-x-5' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex space-x-2">
                <Button
                  onClick={handleCreateSession}
                  disabled={isCreating || !newSessionName.trim()}
                  size="sm"
                  className="flex-1"
                >
                  {isCreating ? 'Creating...' : 'Create Session'}
                </Button>
                <Button
                  onClick={() => setShowCreateForm(false)}
                  variant="outline"
                  size="sm"
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-center text-text-secondary">
            Loading sessions...
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-4 text-center text-text-secondary">
            {searchTerm ? 'No sessions match your search.' : 'No writing sessions yet.'}
          </div>
        ) : (
          <div className="space-y-1 p-2">
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                className={`group relative p-3 rounded-lg cursor-pointer transition-colors ${
                  currentSession?.id === session.id
                    ? 'bg-primary/10 border border-primary/20'
                    : 'hover:bg-muted border border-transparent'
                }`}
                onClick={() => selectSession(session.id)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <FileText className="h-4 w-4 text-text-tertiary flex-shrink-0" />
                      <h3 className="text-sm font-medium text-text-primary truncate">
                        {session.name}
                      </h3>
                    </div>
                    
                    <div className="space-y-1">
                      {session.document_group_id && (
                        <div className="flex items-center space-x-1 text-xs text-text-secondary">
                          <Folder className="h-3 w-3" />
                          <span>
                            {documentGroups.find(g => g.id === session.document_group_id)?.name || 'Unknown Group'}
                          </span>
                        </div>
                      )}
                      
                      <div className="flex items-center space-x-1 text-xs text-text-secondary">
                        <Calendar className="h-3 w-3" />
                        <span>
                          {formatDate(session.updated_at)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Delete Button */}
                  {deleteConfirm === session.id ? (
                    <div className="flex space-x-1">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteConfirm(null)
                        }}
                        className="h-6 px-2 text-xs"
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteSession(session.id)
                        }}
                        className="h-6 px-2 text-xs"
                      >
                        Delete
                      </Button>
                    </div>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 h-auto"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteConfirm(session.id)
                      }}
                    >
                      <Trash2 className="h-3 w-3 text-text-tertiary hover:text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
