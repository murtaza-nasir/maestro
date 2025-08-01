import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useWritingStore } from '../store'
import { useViewStore } from '../../../stores/viewStore'
import { getDocumentGroups } from '../../documents/api'
import type { DocumentGroup } from '../../documents/types'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent } from '../../../components/ui/card'
import { useToast } from '../../../components/ui/toast'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select'
import { 
  Plus, 
  Search,
  FileText,
  Folder,
  Trash2,
} from 'lucide-react'

export const WritingSessionsSidebar: React.FC = React.memo(() => {
  const [searchQuery, setSearchQuery] = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newSessionName, setNewSessionName] = useState('')
  const [selectedDocumentGroup, setSelectedDocumentGroup] = useState<string>('none')
  const [webSearchEnabled, setWebSearchEnabled] = useState(true)
  const [documentGroups, setDocumentGroups] = useState<DocumentGroup[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const { addToast } = useToast()

  const {
    sessions,
    currentSession,
    getSessionLoading,
    loadSessions,
    createSession,
    selectSession,
    deleteSession
  } = useWritingStore()
  
  // Get loading state for sessions (use a special key for general loading)
  const isLoading = getSessionLoading('sessions_loading')

  const { setView } = useViewStore()
  const navigate = useNavigate()
  const location = useLocation()

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

  const filteredSessions = sessions.filter(session =>
    session.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleNewSession = useCallback(() => {
    setShowCreateForm(true)
  }, [])

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
        document_group_id: selectedDocumentGroup === 'none' ? null : selectedDocumentGroup,
        web_search_enabled: webSearchEnabled
      })

      // Reset form
      setNewSessionName('')
      setSelectedDocumentGroup('none')
      setWebSearchEnabled(true)
      setShowCreateForm(false)

      // Navigate to writing view - the store will have the new session as current
      setView('writing')
      
      if (location.pathname !== '/app') {
        navigate('/app')
      }

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

  const handleSessionSelect = useCallback(async (sessionId: string) => {
    try {
      await selectSession(sessionId)
      setView('writing')
      
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error('Failed to select session:', error)
    }
  }, [selectSession, setView, navigate, location.pathname])


  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (window.confirm('Are you sure you want to delete this writing session?')) {
      try {
        const isCurrentSession = currentSession?.id === sessionId
        await deleteSession(sessionId)
        addToast({
          type: 'success',
          title: 'Session Deleted',
          message: 'Writing session has been deleted.',
          duration: 3000
        })
        if (isCurrentSession) {
          setView('writing')
          navigate('/app')
        }
      } catch (error) {
        console.error('Failed to delete session:', error)
        addToast({
          type: 'error',
          title: 'Deletion Failed',
          message: 'Failed to delete writing session.',
          duration: 3000
        })
      }
    }
  }

  const formatRelativeTime = (date: Date | string) => {
    const now = new Date()
    const dateObj = typeof date === 'string' ? new Date(date) : date
    const diffInHours = Math.floor((now.getTime() - dateObj.getTime()) / (1000 * 60 * 60))
    
    if (diffInHours < 1) return 'Just now'
    if (diffInHours < 24) return `${diffInHours}h ago`
    if (diffInHours < 48) return 'Yesterday'
    
    const diffInDays = Math.floor(diffInHours / 24)
    if (diffInDays < 7) return `${diffInDays}d ago`
    
    return dateObj.toLocaleDateString()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 min-h-[88px] flex items-center">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center space-x-2">
            <FileText className="h-5 w-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900">Writing</h2>
          </div>
          
          <Button variant="outline" size="sm" onClick={handleNewSession} className="text-xs">
            <Plus className="h-3 w-3 mr-1" />
            New
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="p-4 border-b border-gray-200">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search sessions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          />
        </div>
      </div>

      {/* Create Session Form */}
      {showCreateForm && (
        <div className="p-4 border-b border-gray-200">
          <Card>
            <CardContent className="p-4 space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
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
                <label className="text-sm font-medium text-gray-700 mb-1 block">
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
                <label className="text-sm font-medium text-gray-700">
                  Enable Web Search
                </label>
                <button
                  type="button"
                  onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                    webSearchEnabled ? 'bg-blue-600' : 'bg-gray-200'
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
        </div>
      )}

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="text-center py-8">
            <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 text-sm">Loading sessions...</p>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center py-8">
            <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 text-sm">
              {searchQuery ? 'No sessions found' : 'No writing sessions yet'}
            </p>
            {!searchQuery && (
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handleNewSession}
                className="mt-2"
              >
                Start your first session
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredSessions.map((session) => {
              const isActive = currentSession?.id === session.id
              
              return (
                <div
                  key={session.id}
                  className={`group relative p-3 rounded-lg cursor-pointer border transition-colors ${
                    isActive 
                      ? 'border-blue-200 bg-blue-50' 
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                  onClick={() => handleSessionSelect(session.id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-gray-900 truncate">
                        {session.name}
                      </div>
                      <div className="text-xs text-gray-400 mt-1 space-y-1">
                        <div>{formatRelativeTime(session.updated_at)}</div>
                        {session.document_group_id && (
                          <div className="flex items-center space-x-1">
                            <Folder className="h-3 w-3" />
                            <span>
                              {documentGroups.find(g => g.id === session.document_group_id)?.name || 'Unknown Group'}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-red-500 hover:text-red-700"
                        onClick={(e) => handleDelete(session.id, e)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
})

WritingSessionsSidebar.displayName = 'WritingSessionsSidebar'
