import React, { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { useChatStore } from '../store'
import { useMissionStore } from '../../mission/store'
import { getDocumentGroups } from '../../documents/api'
import type { DocumentGroup } from '../../documents/types'
import { Button } from '../../../components/ui/button'
import { Card, CardContent } from '../../../components/ui/card'
import { PanelHeader } from '../../../components/ui/PanelHeader'
import { PanelControls } from '../../../components/ui/PanelControls'
import { usePanelControls } from '../../../components/layout/SplitPaneLayout'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select'
import { useToast } from '../../../components/ui/toast'
import { Send, Loader2, Bot, User, Sparkles, Settings } from 'lucide-react'
import { buildApiUrl, API_CONFIG } from '../../../config/api'
import { MissionSettingsDialog } from '../../mission/components/MissionSettingsDialog'
import { formatChatMessageTime } from '../../../utils/timezone'
import { useTheme } from '../../../contexts/ThemeContext'

interface ChatPanelProps {
  chatId?: string
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ chatId: propChatId }) => {
  const { t } = useTranslation()
  const { chatId: paramChatId } = useParams<{ chatId: string }>()
  const chatId = propChatId || paramChatId
  
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [documentGroups, setDocumentGroups] = useState<DocumentGroup[]>([])
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [useWebSearch, setUseWebSearch] = useState<boolean>(true)
  const [showMissionSettings, setShowMissionSettings] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { addToast } = useToast()
  
  let panelControls = null
  try {
    panelControls = usePanelControls()
  } catch {
    // Not in SplitPaneLayout context
  }
  
  const { 
    chats, 
    activeChat, 
    isLoading: chatLoading,
    createChat, 
    setActiveChat, 
    addMessage, 
    updateChatTitle,
    associateMissionWithChat
  } = useChatStore()

  const { missions, clearActiveMission } = useMissionStore()
  
  const currentMission = activeChat?.missionId
    ? missions.find(m => m.id === activeChat.missionId)
    : null
  
  const isChatDisabled = isLoading || 
    (currentMission?.status === 'running') || 
    (currentMission?.status === 'completed') ||
    (currentMission?.status === 'failed') ||
    (currentMission?.status === 'stopped')

  const currentChat = chatId 
    ? (activeChat?.id === chatId ? activeChat : chats.find(c => c.id === chatId))
    : activeChat

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [currentChat?.messages])

  useEffect(() => {
    if (chatId && chatId !== activeChat?.id) {
      setActiveChat(chatId)
      setIsLoading(false)
    }
  }, [chatId, activeChat?.id, setActiveChat])

  useEffect(() => {
    clearActiveMission()
  }, [clearActiveMission])

  useEffect(() => {
    const fetchGroups = async () => {
      try {
        const groups = await getDocumentGroups();
        setDocumentGroups(groups);
      } catch (error) {
        console.error("Failed to fetch document groups", error);
      }
    };
    fetchGroups();
  }, []);

  useEffect(() => {
    if (currentChat?.missionId) {
      useMissionStore.getState().ensureMissionInStore(currentChat.missionId)
      
      if (panelControls?.isRightPanelCollapsed) {
        panelControls.toggleRightPanel()
      }
    }
  }, [currentChat?.missionId, panelControls])

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading) return

    if (!useWebSearch && !selectedGroupId) {
      addToast({
        type: 'error',
        title: t('chat.noInformationSource'),
        message: t('chat.noInformationSourceDescription'),
        duration: 5000
      })
      return
    }

    let targetChatId = activeChat?.id;
    const isFirstMessageInNewChat = !targetChatId;

    if (isFirstMessageInNewChat) {
      try {
        const newChat = await createChat();
        targetChatId = newChat.id;
        setActiveChat(newChat.id);
      } catch (error) {
        console.error('Failed to create chat:', error);
        setIsLoading(false);
        return;
      }
    }

    const isFirstMessage = isFirstMessageInNewChat || (currentChat?.messages.length === 0);
    const userMessage = message.trim()
    setMessage('')
    setIsLoading(true)

    if (targetChatId) {
      try {
        await addMessage(targetChatId, {
          content: userMessage,
          role: 'user'
        })
      } catch (error) {
        console.error('Failed to add user message:', error)
        setIsLoading(false)
        return
      }
    }

    try {
      if (isFirstMessage && targetChatId) {
        const title = userMessage.length > 50 
          ? userMessage.substring(0, 50) + '...'
          : userMessage
        updateChatTitle(targetChatId, title)
      }

      const updatedCurrentChat = useChatStore.getState().chats.find(c => c.id === targetChatId);
      const conversationHistory = updatedCurrentChat?.messages.map(msg => ({
        role: msg.role,
        content: msg.content
      })) || []

      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.CHAT.SEND), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        credentials: 'include',
        body: JSON.stringify({
          message: userMessage,
          chat_id: targetChatId,
          conversation_history: conversationHistory,
          mission_id: updatedCurrentChat?.missionId || null,
          document_group_id: selectedGroupId,
          use_web_search: useWebSearch
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        
        if (errorData.detail && typeof errorData.detail === 'object') {
          const { error, message } = errorData.detail
          
          addToast({
            type: 'error',
            title: error || t('chat.chatError'),
            message: message || t('chat.errorMessage'),
            duration: 8000
          })
          
          throw new Error(message || t('chat.failedToProcess'))
        } else {
          const errorMessage = errorData.detail || `HTTP ${response.status}: ${response.statusText}`
          addToast({
            type: 'error',
            title: t('chat.chatError'),
            message: errorMessage,
            duration: 8000
          })
          throw new Error(errorMessage)
        }
      }

      const data = await response.json()
      
      if (targetChatId) {
        await addMessage(targetChatId, {
          content: data.response,
          role: 'assistant'
        })

        if (data.updated_title) {
          await updateChatTitle(targetChatId, data.updated_title)
        }

        if (data.action) {
          await handleAgentAction(data.action, data.request, data.mission_id, targetChatId)
        }
      }
      
      setIsLoading(false)
      
    } catch (error) {
      console.error('Error sending message:', error)
      let errorMessage = t('chat.genericError')
      
      if (error instanceof Error) {
        if (error.message.includes('503')) {
          errorMessage = t('chat.serviceUnavailable')
        } else if (error.message.includes('401')) {
          errorMessage = t('chat.sessionExpired')
        } else if (error.message.includes('Failed to fetch')) {
          errorMessage = t('chat.connectionError')
        }
      }
      
      if (targetChatId) {
        await addMessage(targetChatId, {
          content: errorMessage,
          role: 'assistant'
        })
      }
      setIsLoading(false)
    }
  }

  const handleAgentAction = async (action: string, request: string | null, missionId: string | null, chatId: string) => {
    try {
      switch (action) {
        case 'start_research':
          if (missionId) {
            associateMissionWithChat(chatId, missionId)
            
            addToast({
              type: 'success',
              title: t('chat.researchMissionStarted'),
              message: t('chat.researchMissionStartedDescription'),
              duration: 5000
            })

            if (panelControls?.isRightPanelCollapsed) {
              panelControls.toggleRightPanel()
            }

            await generateInitialQuestions(missionId, request || '')
          }
          break
          
        case 'refine_questions':
          if (missionId && request) {
            await refineQuestions(missionId, request)
          }
          break
          
        case 'approve_questions':
          if (missionId) {
            await approveAndStartResearch(missionId)
            useMissionStore.getState().fetchMissionStatus(missionId)
          }
          break
          
        default:
          break
      }
    } catch (error) {
      console.error('Error handling agent action:', error)
      addToast({
        type: 'error',
        title: t('chat.actionError'),
        message: t('chat.actionErrorDescription'),
        duration: 5000
      })
    }
  }

  const generateInitialQuestions = async (missionId: string, researchTopic: string) => {
    try {
      const response = await fetch(buildApiUrl('/api/chat/generate-questions'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        credentials: 'include',
        body: JSON.stringify({
          mission_id: missionId,
          research_topic: researchTopic
        })
      })

      if (response.ok) {
        addToast({
          type: 'info',
          title: t('chat.questionsGenerated'),
          message: t('chat.questionsGeneratedDescription'),
          duration: 5000
        })
      }
    } catch (error) {
      console.error('Error generating questions:', error)
    }
  }

  const refineQuestions = async (_missionId: string, _feedback: string) => {
    addToast({
      type: 'info',
      title: t('chat.refiningQuestions'),
      message: t('chat.refiningQuestionsDescription'),
      duration: 3000
    })
  }

  const approveAndStartResearch = async (_missionId: string) => {
    try {
      addToast({
        type: 'success',
        title: t('chat.researchStarted'),
        message: t('chat.researchStartedDescription'),
        duration: 5000
      })
    } catch (error) {
      console.error('Error starting research:', error)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  if (chatLoading && !currentChat) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center max-w-md mx-auto p-8">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
            <Loader2 className="h-8 w-8 text-primary animate-spin" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-4">
            {t('chat.loadingChat')}
          </h2>
          <p className="text-muted-foreground mb-6">
            {t('chat.loadingChatDescription')}
          </p>
        </div>
      </div>
    )
  }

  if (!currentChat) {
    const { theme } = useTheme()
    
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center max-w-md mx-auto p-8">
          <div className="flex justify-center mb-6">
            <img 
              src={theme === 'dark' ? '/icon_dark.png' : '/icon_original.png'} 
              alt="MAESTRO Logo" 
              className="h-16 w-16 transition-transform hover:scale-105"
            />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-4">
            {t('chat.welcome')}
          </h2>
          <p className="text-muted-foreground mb-6">
            {t('chat.welcomeDescription')}
          </p>
          <Button 
            onClick={async () => {
              try {
                const newChat = await createChat()
                await setActiveChat(newChat.id)
              } catch (error) {
                console.error('Failed to create new chat:', error)
              }
            }}
            className="inline-flex items-center"
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {t('chat.startNewChat')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background">
      <PanelHeader
        title={currentChat.title}
        subtitle={currentChat.messages.length === 0 
          ? t('chat.startConversation')
          : t('chat.messageCount', { count: currentChat.messages.length })
        }
        actions={
          <div className="flex items-center space-x-4">
            <PanelControls
              onTogglePanel={panelControls?.toggleRightPanel}
              isCollapsed={panelControls?.isRightPanelCollapsed}
              showToggle={true}
              toggleTooltip={t('chat.hideResearchPanel')}
            />
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto space-y-4">
          {currentChat.messages.length === 0 ? (
            <div className="text-center py-8">
              <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-3">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-2">
                {t('chat.readyToHelp')}
              </h3>
              <p className="text-muted-foreground text-xs max-w-sm mx-auto">
                {t('chat.readyToHelpDescription')}
              </p>
            </div>
          ) : (
            currentChat.messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`flex max-w-xs lg:max-w-2xl ${
                  msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                } items-start space-x-2`}>
                  <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                    msg.role === 'user' 
                      ? 'bg-primary text-primary-foreground ml-2' 
                      : 'bg-muted mr-2'
                  }`}>
                    {msg.role === 'user' ? (
                      <User className="h-3.5 w-3.5" />
                    ) : (
                      <Bot className="h-3.5 w-3.5 text-text-secondary" />
                    )}
                  </div>
                  
                  <div className={`px-3 py-2 rounded-xl ${
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground rounded-br-md'
                      : 'bg-card border border-border text-text-primary rounded-bl-md shadow-sm'
                  }`}>
                    <div className="prose prose-xs max-w-none text-current text-sm">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          a: ({node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" className={msg.role === 'user' ? "text-primary-foreground/80 hover:underline" : "text-primary hover:underline"} />,
                          ul: ({node, ...props}) => <ul {...props} className="my-1 space-y-0.5" />,
                          ol: ({node, ...props}) => <ol {...props} className="my-1 space-y-0.5" />,
                          li: ({node, ...props}) => <li {...props} className="ml-4" />,
                          p: ({node, ...props}) => <p {...props} className="mb-1 last:mb-0 break-words leading-relaxed" />,
                          h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-1 mt-2 first:mt-0" />,
                          h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-1 mt-1.5 first:mt-0" />,
                          h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-0.5 mt-1 first:mt-0" />,
                          h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          blockquote: ({node, ...props}) => (
                            <blockquote 
                              {...props} 
                              className={`border-l-4 pl-4 my-1.5 italic ${
                                msg.role === 'user' ? 'border-primary-foreground/50' : 'border-border'
                              }`} 
                            />
                          ),
                          hr: ({node, ...props}) => (
                            <hr {...props} className="my-1.5 border-border" />
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                    <p className={`text-xs mt-1 ${
                      msg.role === 'user' ? 'text-primary-foreground/80' : 'text-muted-foreground'
                    }`} style={{ fontSize: '0.7rem', opacity: 0.8 }}>
                      {formatChatMessageTime(msg.timestamp)}
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="flex items-start space-x-2">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-muted flex items-center justify-center">
                  <Bot className="h-3.5 w-3.5 text-text-secondary" />
                </div>
                <div className="bg-card border border-border text-text-primary max-w-xs lg:max-w-2xl px-3 py-2 rounded-xl rounded-bl-md shadow-sm">
                  <div className="flex items-center space-x-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                    <span className="text-xs text-text-tertiary">{t('chat.thinking')}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="bg-card border-t border-border p-4">
        <div className="max-w-4xl mx-auto">
          {currentMission?.status === 'completed' && (
            <div className="mb-3 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <p className="text-sm text-green-600 dark:text-green-400 font-medium">
                  {t('chat.missionCompleted')}
                </p>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {t('chat.missionCompletedDescription')}
              </p>
            </div>
          )}
          {currentMission?.status === 'failed' && (
            <div className="mb-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                <p className="text-sm text-red-600 dark:text-red-400 font-medium">
                  {t('chat.missionFailed')}
                </p>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {t('chat.missionFailedDescription')}
              </p>
            </div>
          )}
          {currentMission?.status === 'stopped' && (
            <div className="mb-3 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
                <p className="text-sm text-yellow-600 dark:text-yellow-400 font-medium">
                  {t('chat.missionStopped')}
                </p>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {t('chat.missionStoppedDescription')}
              </p>
            </div>
          )}
          <Card className={
            (currentMission?.status === 'completed' || 
             currentMission?.status === 'failed' || 
             currentMission?.status === 'stopped') ? 'opacity-60' : ''
          }>
            <CardContent className="p-4">
              <div className="flex flex-col">
                <div className="flex space-x-4">
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder={
                      currentMission?.status === 'completed' ? t('chat.missionCompletedDisabled') :
                      currentMission?.status === 'failed' ? t('chat.missionFailedDisabled') :
                      currentMission?.status === 'stopped' ? t('chat.missionStoppedDisabled') :
                      currentMission?.status === 'running' ? t('chat.missionRunning') :
                      t('chat.typeMessage')
                    }
                    className="flex-1 resize-none border-0 focus:ring-0 focus:outline-none text-xs min-h-[18px] max-h-28 bg-transparent"
                    rows={1}
                    disabled={isChatDisabled}
                    style={{
                      height: 'auto',
                      minHeight: '20px'
                    }}
                    onInput={(e) => {
                      const target = e.target as HTMLTextAreaElement
                      target.style.height = 'auto'
                      target.style.height = target.scrollHeight + 'px'
                    }}
                  />
                  <Button
                    onClick={handleSendMessage}
                    disabled={!message.trim() || isChatDisabled}
                    size="sm"
                    className="self-end"
                  >
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <div className="mt-2 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex items-center space-x-1.5 min-w-0">
                      <label className="text-xs text-muted-foreground whitespace-nowrap">{t('chat.documentGroup')}</label>
                      <Select
                        value={selectedGroupId || ''}
                        onValueChange={(value) => {
                          if (value === "none") {
                            setSelectedGroupId(null);
                          } else {
                            setSelectedGroupId(value);
                          }
                        }}
                        disabled={isChatDisabled}
                      >
                        <SelectTrigger className="text-xs h-6 w-[110px]">
                          <SelectValue placeholder={t('chat.none')} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t('chat.none')}</SelectItem>
                          {documentGroups.map((group) => (
                            <SelectItem key={group.id} value={group.id}>
                              {group.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="flex items-center space-x-1.5">
                      <label className="text-xs text-muted-foreground whitespace-nowrap">{t('chat.webSearch')}</label>
                      <button
                        type="button"
                        onClick={() => setUseWebSearch(!useWebSearch)}
                        disabled={isChatDisabled}
                        className={`relative inline-flex h-3.5 w-6 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                          useWebSearch ? 'bg-primary' : 'bg-secondary'
                        } ${isChatDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                      >
                        <span
                          className={`inline-block h-2 w-2 transform rounded-full bg-white transition-transform ${
                            useWebSearch ? 'translate-x-3' : 'translate-x-0.5'
                          }`}
                        />
                      </button>
                      <span className={`text-xs ${useWebSearch ? 'text-primary' : 'text-muted-foreground'}`}>
                        {useWebSearch ? t('chat.on') : t('chat.off')}
                      </span>
                    </div>

                    {currentMission && (
                      <div className="flex items-center space-x-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowMissionSettings(true)}
                          disabled={isChatDisabled}
                          className="h-6 px-2 text-xs"
                        >
                          <Settings className="h-2.5 w-2.5 mr-1" />
                          {t('chat.settings')}
                        </Button>
                      </div>
                    )}
                  </div>
                  
                  {!useWebSearch && !selectedGroupId && (
                    <div className="text-xs text-amber-600 bg-amber-500/10 px-2 py-1.5 rounded-md border border-amber-500/20 flex items-center space-x-1.5">
                      <span>⚠️</span>
                      <span>{t('chat.informationSourceWarning')}</span>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
          
          <p className="text-xs text-muted-foreground mt-1.5 text-center">
            {t('chat.keyPressHint')}
          </p>
        </div>
      </div>

      {currentMission && (
        <MissionSettingsDialog
          isOpen={showMissionSettings}
          onOpenChange={setShowMissionSettings}
          missionId={currentMission.id}
        />
      )}
    </div>
  )
}
