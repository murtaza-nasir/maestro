import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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

  const { containerRef, saveScrollPosition } = useScrollPosition({
    key: 'chat-history-sidebar',
    dependencies: [activeChat?.id]
  })

  useEffect(() => {
    loadChats()
  }, [loadChats])

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
      
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error('Failed to create new chat:', error)
    }
  }, [createChat, setView, navigate, location.pathname])

  const handleChatSelect = useCallback(async (chatId: string) => {
    try {
      saveScrollPosition()
      
      await setActiveChat(chatId)
      setView('research')
      
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
    
    if (diffInHours < 1) return t('chatHistory.justNow')
    if (diffInHours < 24) return t('chatHistory.hoursAgo', { count: diffInHours })
    if (diffInHours < 48) return t('chatHistory.yesterday')
    
    const diffInDays = Math.floor(diffInHours / 24)
    if (diffInDays < 7) return t('chatHistory.daysAgo', { count: diffInDays })
    
    return dateObj.toLocaleDateString()
  }

  return (
    <>
      <div className="flex flex-col h-full bg-sidebar-background">
        <div className="px-4 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-1.5">
              <MessageSquare className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-medium text-foreground">{t('chatHistory.chats')}</h2>
            </div>

            <Button variant="outline" size="sm" onClick={handleNewChat} className="text-xs h-7 px-2">
              <Plus className="h-3 w-3 mr-1" />
              {t('chatHistory.new')}
            </Button>
          </div>
        </div>

        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder={t('chatHistory.searchChats')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background"
            />
          </div>
        </div>

        <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
          {filteredChats.length === 0 ? (
            <div className="text-center py-8">
              <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground text-sm">
                {searchQuery ? t('chatHistory.noChatsFound') : t('chatHistory.noChatsYet')}
              </p>
              {!searchQuery && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleNewChat}
                  className="mt-2"
                >
                  {t('chatHistory.startFirstChat')}
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
                    label: t('chatHistory.edit'),
                    onClick: (e: React.MouseEvent) => handleEditStart(chat, e)
                  },
                  {
                    icon: <Trash2 className="h-3 w-3" />,
                    label: t('chatHistory.delete'),
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

      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title={t('chatHistory.deleteChat')}
        description={t('chatHistory.deleteChatConfirmation')}
        itemName={chatToDelete?.title}
        itemType="chat"
        isLoading={isDeleting}
      />
    </>
  )
})

ChatHistorySidebar.displayName = 'ChatHistorySidebar'
