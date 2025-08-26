import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useLocation } from 'react-router-dom'
import { useWritingStore } from '../store'
import { useViewStore } from '../../../stores/viewStore'
import { useScrollPosition } from '../../../hooks/useScrollPosition'
import { Button } from '../../../components/ui/button'
import { ListItem, createEditAction, createDeleteAction } from '../../../components/ui/ListItem'
import { DeleteConfirmationModal } from '../../../components/ui/DeleteConfirmationModal'
import { 
  Plus, 
  Search,
  PenTool,
  FileText
} from 'lucide-react'
import { apiClient } from '../../../config/api'

interface WritingChatSidebarProps {}

export const WritingChatSidebar: React.FC<WritingChatSidebarProps> = React.memo(() => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('')
  const [editingChatId, setEditingChatId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState<{ id: string; title: string } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  
  const { 
    chats, 
    activeChat, 
    isLoading, 
    loadChats, 
    createChat, 
    setActiveChat, 
    deleteChat 
  } = useWritingStore()
  
  const { setView } = useViewStore()
  const navigate = useNavigate()
  const location = useLocation()

  const { containerRef, saveScrollPosition } = useScrollPosition({
    key: 'writing-chat-sidebar',
    dependencies: [activeChat?.id]
  })

  useEffect(() => {
    loadChats()
  }, [loadChats])

  useEffect(() => {
    const handleChatTitleUpdate = (event: CustomEvent) => {
      loadChats()
    }

    window.addEventListener('writingChatTitleUpdate', handleChatTitleUpdate as EventListener)
    
    return () => {
      window.removeEventListener('writingChatTitleUpdate', handleChatTitleUpdate as EventListener)
    }
  }, [loadChats])

  const filteredChats = chats.filter(chat =>
    chat.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleNewChat = useCallback(async () => {
    try {
      await createChat(t('writingChatSidebar.newWritingChat'))
      setView('writing')
      
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error(t('writingChatSidebar.failedToCreate'), error)
    }
  }, [createChat, setView, navigate, location.pathname, t])

  const handleChatSelect = useCallback(async (chatId: string) => {
    try {
      saveScrollPosition()
      
      await setActiveChat(chatId)
      setView('writing')
      
      if (location.pathname !== '/app') {
        navigate('/app')
      }
    } catch (error) {
      console.error(t('writingChatSidebar.failedToSelect'), error)
    }
  }, [setActiveChat, setView, saveScrollPosition, navigate, location.pathname, t])

  const handleEditStart = (chat: any, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingChatId(chat.id)
    setEditTitle(chat.title)
  }

  const handleEditSave = async (chatId: string) => {
    if (editTitle.trim()) {
      try {
        await apiClient.put(`/api/chats/${chatId}`, {
          title: editTitle.trim()
        })
        
        await loadChats()
      } catch (error) {
        console.error(t('writingChatSidebar.failedToUpdate'), error)
      }
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
      await deleteChat(chatToDelete.id)
      
      setDeleteModalOpen(false)
      setChatToDelete(null)
    } catch (error) {
      console.error(t('writingChatSidebar.failedToDelete'), error)
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
    
    if (diffInHours < 1) return t('writingChatSidebar.justNow');
    if (diffInHours < 24) return t('writingChatSidebar.hoursAgo', { count: diffInHours });
    if (diffInHours < 48) return t('writingChatSidebar.yesterday');
    
    const diffInDays = Math.floor(diffInHours / 24)
    if (diffInDays < 7) return t('writingChatSidebar.daysAgo', { count: diffInDays });
    
    return dateObj.toLocaleDateString()
  }

  return (
    <>
      <div className="flex flex-col h-full bg-sidebar-background">
        <div className="px-4 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-1.5">
              <FileText className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-medium text-text-primary">{t('writingChatSidebar.writing')}</h2>
            </div>

            <Button variant="outline" size="sm" onClick={handleNewChat} className="text-xs h-7 px-2">
              <Plus className="h-3 w-3 mr-1" />
              {t('writingChatSidebar.new')}
            </Button>
          </div>
        </div>

        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
            <input
              type="text"
              placeholder={t('writingChatSidebar.searchSessions')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
            />
          </div>
        </div>

        <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
              <p className="text-text-secondary text-sm mt-2">{t('writingChatSidebar.loading')}</p>
            </div>
          ) : filteredChats.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="h-12 w-12 text-muted-foreground/20 mx-auto mb-4" />
              <p className="text-text-secondary text-sm">
                {searchQuery ? t('writingChatSidebar.noSessionsFound') : t('writingChatSidebar.noSessionsYet')}
              </p>
              {!searchQuery && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleNewChat}
                  className="mt-2"
                >
                  {t('writingChatSidebar.startFirstSession')}
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
                      className="p-2 rounded-md border border-primary bg-primary/5"
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
                        className="w-full text-xs font-medium bg-background border border-border rounded px-2 py-1 focus:ring-2 focus:ring-primary focus:border-transparent"
                        autoFocus
                      />
                    </div>
                  )
                }

                const actions = [
                  createEditAction((e: React.MouseEvent) => handleEditStart(chat, e)),
                  createDeleteAction((e: React.MouseEvent) => handleDeleteClick(chat.id, chat.title, e))
                ]

                return (
                  <ListItem
                    key={chat.id}
                    isSelected={isActive}
                    onClick={() => handleChatSelect(chat.id)}
                    icon={<PenTool className="h-4 w-4" />}
                    title={chat.title}
                    timestamp={formatRelativeTime(chat.updated_at)}
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
        title={t('writingChatSidebar.deleteSession')}
        description={t('writingChatSidebar.deleteSessionConfirmation')}
        itemName={chatToDelete?.title}
        itemType="session"
        isLoading={isDeleting}
      />
    </>
  )
})

WritingChatSidebar.displayName = 'WritingChatSidebar'
