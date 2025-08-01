import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useChatStore } from '../store'
import { useViewStore } from '../../../stores/viewStore'
import { useScrollPosition } from '../../../hooks/useScrollPosition'
import { Button } from '../../../components/ui/button'
import { ListItem } from '../../../components/ui/ListItem'
import { DeleteConfirmationModal } from '../../../components/ui/DeleteConfirmationModal'
import { 
  Plus, 
  Search,
  MessageSquare,
  Trash2,
  Edit2,
} from 'lucide-react'

interface ChatHistorySidebarProps {}

export const ChatHistorySidebar: React.FC<ChatHistorySidebarProps> = React.memo(() => {
  const [searchQuery, setSearchQuery] = useState('')
  const [editingChatId, setEditingChatId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState<{ id: string; title: string } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  
  const { 
    chats, 
    activeChat, 
    loadChats,
    createChat, 
    setActiveChat, 
    updateChatTitle, 
    deleteChat,
    clearError
  } = useChatStore()
  
  const { setView } = useViewStore()
  const navigate = useNavigate()
  const location = useLocation()

  // Use scroll position hook to preserve scroll position during chat switching
  const { containerRef, saveScrollPosition } = useScrollPosition({
    key: 'chat-history-sidebar',
    dependencies: [activeChat?.id]
  })

  // Load chats on component mount
  useEffect(() => {
    loadChats()
  }, [loadChats])

  // Clear error when component unmounts
  useEffect(() => {
    return () => clearError()
  }, [clearError])

  const filteredChats = chats.filter(chat =>
    chat.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    chat.messages.some(msg => 
      msg.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
  )

  const handleNewChat = useCallback(async () => {
    try {
      await createChat()
      setView('research')
      
      // Navigate to /app if we're not already there
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error('Failed to create new chat:', error)
    }
  }, [createChat, setView, navigate, location.pathname])

  const handleChatSelect = useCallback(async (chatId: string) => {
    try {
      // Save scroll position before switching chats
      saveScrollPosition()
      
      await setActiveChat(chatId)
      setView('research')
      
      // Navigate to /app if we're not already there
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error('Failed to select chat:', error)
    }
  }, [setActiveChat, setView, saveScrollPosition, navigate, location.pathname])

  const handleEditStart = (chat: any, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingChatId(chat.id)
    setEditTitle(chat.title)
  }

  const handleEditSave = (chatId: string) => {
    if (editTitle.trim()) {
      updateChatTitle(chatId, editTitle.trim())
    }
    setEditingChatId(null)
    setEditTitle('')
  }

  const handleEditCancel = () => {
    setEditingChatId(null)
    setEditTitle('')
  }

  const handleDeleteClick = (chatId: string, chatTitle: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setChatToDelete({ id: chatId, title: chatTitle })
    setDeleteModalOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!chatToDelete) return
    
    try {
      setIsDeleting(true)
      const isCurrentChat = activeChat?.id === chatToDelete.id
      await deleteChat(chatToDelete.id)
      
      if (isCurrentChat) {
        setView('research')
        navigate('/app')
      }
      
      setDeleteModalOpen(false)
      setChatToDelete(null)
    } catch (error) {
      console.error('Failed to delete chat:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleDeleteCancel = () => {
    setDeleteModalOpen(false)
    setChatToDelete(null)
    setIsDeleting(false)
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
    <>
      <div className="flex flex-col h-full bg-sidebar-background">
      {/* Header */}
      <div className="px-4 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center space-x-1.5">
            <MessageSquare className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-medium text-foreground">Chats</h2>
          </div>
          
          <Button variant="outline" size="sm" onClick={handleNewChat} className="text-xs h-7 px-2">
            <Plus className="h-3 w-3 mr-1" />
            New
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background"
          />
        </div>
      </div>

      {/* Chat List */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
        {filteredChats.length === 0 ? (
          <div className="text-center py-8">
            <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground text-sm">
              {searchQuery ? 'No chats found' : 'No chats yet'}
            </p>
            {!searchQuery && (
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handleNewChat}
                className="mt-2"
              >
                Start your first chat
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {filteredChats.map((chat) => {
              const isActive = activeChat?.id === chat.id
              
              if (editingChatId === chat.id) {
                return (
                  <div
                    key={chat.id}
                    className="p-3 rounded-lg border border-primary bg-primary/5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSave(chat.id)
                        if (e.key === 'Escape') handleEditCancel()
                      }}
                      onBlur={() => handleEditSave(chat.id)}
                      className="w-full text-sm font-medium bg-background border border-border rounded px-2 py-1 focus:ring-2 focus:ring-primary focus:border-transparent"
                      autoFocus
                    />
                  </div>
                )
              }

              const actions = [
                {
                  icon: <Edit2 className="h-3 w-3" />,
                  label: 'Edit',
                  onClick: (e: React.MouseEvent) => handleEditStart(chat, e)
                },
                {
                  icon: <Trash2 className="h-3 w-3" />,
                  label: 'Delete',
                  onClick: (e: React.MouseEvent) => handleDeleteClick(chat.id, chat.title, e),
                  variant: 'destructive' as const
                }
              ]
              
              return (
                <ListItem
                  key={chat.id}
                  isSelected={isActive}
                  onClick={() => handleChatSelect(chat.id)}
                  icon={<MessageSquare className="h-4 w-4" />}
                  title={chat.title}
                  timestamp={formatRelativeTime(chat.updatedAt)}
                  actions={actions}
                  showActionsPermanently={true}
                />
              )
            })}
          </div>
        )}
      </div>
      </div>

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Chat"
        description="Are you sure you want to delete this chat? All messages and conversation history will be permanently removed."
        itemName={chatToDelete?.title}
        itemType="chat"
        isLoading={isDeleting}
      />
    </>
  )
})

ChatHistorySidebar.displayName = 'ChatHistorySidebar'
