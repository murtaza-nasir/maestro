import React, { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
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
  
  // Get panel controls - use try/catch to handle when not in SplitPaneLayout context
  let panelControls = null
  try {
    panelControls = usePanelControls()
  } catch {
    // Not in SplitPaneLayout context, controls will be disabled
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
  
  // Get the current mission associated with the active chat
  const currentMission = activeChat?.missionId
    ? missions.find(m => m.id === activeChat.missionId)
    : null
  
  // Determine if the chat should be disabled
  const isChatDisabled = isLoading || (currentMission?.status === 'running')

  // Find the current chat - prioritize activeChat if it matches the chatId
  const currentChat = chatId 
    ? (activeChat?.id === chatId ? activeChat : chats.find(c => c.id === chatId))
    : activeChat

  // Auto-scroll to bottom when new messages are added
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [currentChat?.messages])

  // Set active chat when chatId changes
  useEffect(() => {
    if (chatId && chatId !== activeChat?.id) {
      setActiveChat(chatId)
    }
  }, [chatId, activeChat?.id, setActiveChat])

  // Clear any stale global mission on component mount
  useEffect(() => {
    // Clear the global mission since we're now using chat-specific missions
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

  // Ensure mission is loaded when chat with mission is selected
  useEffect(() => {
    if (currentChat?.missionId) {
      useMissionStore.getState().ensureMissionInStore(currentChat.missionId)
      
      // Auto-open the research panel if it's collapsed and we have a mission
      if (panelControls?.isRightPanelCollapsed) {
        panelControls.toggleRightPanel()
      }
    }
  }, [currentChat?.missionId, panelControls])

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading) return

    // Validate that at least one information source is enabled
    if (!useWebSearch && !selectedGroupId) {
      addToast({
        type: 'error',
        title: 'No Information Source',
        message: 'Please enable web search or select a document group before sending your message.',
        duration: 5000
      })
      return
    }

    let targetChatId = activeChat?.id;

    // If no active chat, this is the first message of a new chat.
    const isFirstMessageInNewChat = !targetChatId;

    if (isFirstMessageInNewChat) {
      try {
        const newChat = await createChat();
        targetChatId = newChat.id;
        setActiveChat(newChat.id); // Immediately set the new chat as active
      } catch (error) {
        console.error('Failed to create chat:', error);
        setIsLoading(false);
        return;
      }
    }

    // This check is now more robust.
    const isFirstMessage = isFirstMessageInNewChat || (currentChat?.messages.length === 0);

    const userMessage = message.trim()
    setMessage('')
    setIsLoading(true)

    // Add user message
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
      // Auto-generate chat title from first message
      if (isFirstMessage && targetChatId) {
        const title = userMessage.length > 50 
          ? userMessage.substring(0, 50) + '...'
          : userMessage
        updateChatTitle(targetChatId, title)
      }

      // Refetch the chat from the store to ensure we have the latest state
      const updatedCurrentChat = useChatStore.getState().chats.find(c => c.id === targetChatId);

      // Get conversation history for API call
      const conversationHistory = updatedCurrentChat?.messages.map(msg => ({
        role: msg.role,
        content: msg.content
      })) || []

      // Call the MessengerAgent-integrated chat API using apiClient for proper auth
      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.CHAT.SEND), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        credentials: 'include', // Include cookies for authentication
        body: JSON.stringify({
          message: userMessage,
          chat_id: targetChatId,
          conversation_history: conversationHistory,
          mission_id: updatedCurrentChat?.missionId || null, // Pass existing mission ID if available
          document_group_id: selectedGroupId,
          use_web_search: useWebSearch
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        
        // Handle structured error responses from backend
        if (errorData.detail && typeof errorData.detail === 'object') {
          const { error, message } = errorData.detail
          
          // Show toast notification with detailed error
          addToast({
            type: 'error',
            title: error || 'Chat Error',
            message: message || 'An error occurred while processing your message.',
            duration: 8000 // Show longer for errors
          })
          
          throw new Error(message || 'Failed to process message')
        } else {
          // Handle simple error responses
          const errorMessage = errorData.detail || `HTTP ${response.status}: ${response.statusText}`
          addToast({
            type: 'error',
            title: 'Chat Error',
            message: errorMessage,
            duration: 8000
          })
          throw new Error(errorMessage)
        }
      }

      const data = await response.json()
      
      if (targetChatId) {
        // Add AI response
        addMessage(targetChatId, {
          content: data.response,
          role: 'assistant'
        })

        // Update chat title if it was changed by the backend
        if (data.updated_title) {
          updateChatTitle(targetChatId, data.updated_title)
        }

        // Handle MessengerAgent actions
        if (data.action) {
          await handleAgentAction(data.action, data.request, data.mission_id, targetChatId)
        }
      }
      
      setIsLoading(false)
      
    } catch (error) {
      console.error('Error sending message:', error)
      let errorMessage = 'Sorry, I encountered an error while processing your message. Please try again.'
      
      if (error instanceof Error) {
        if (error.message.includes('503')) {
          errorMessage = 'The AI service is currently unavailable. Please try again in a moment.'
        } else if (error.message.includes('401')) {
          errorMessage = 'Your session has expired. Please refresh the page and log in again.'
        } else if (error.message.includes('Failed to fetch')) {
          errorMessage = 'Unable to connect to the server. Please check your internet connection and try again.'
        }
      }
      
      if (targetChatId) {
        addMessage(targetChatId, {
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
            // Associate the new mission with this chat
            associateMissionWithChat(chatId, missionId)
            
            addToast({
              type: 'success',
              title: 'Research Mission Started',
              message: 'I\'ve created a new research mission. Check the research panel to monitor progress.',
              duration: 5000
            })

            // Auto-open the research panel
            if (panelControls?.isRightPanelCollapsed) {
              panelControls.toggleRightPanel()
            }

            // Generate initial questions for the research topic
            await generateInitialQuestions(missionId, request || '')
          }
          break
          
        case 'refine_questions':
          if (missionId && request) {
            // Handle question refinement
            await refineQuestions(missionId, request)
          }
          break
          
        case 'approve_questions':
          if (missionId) {
            // Handle research approval and start execution
            await approveAndStartResearch(missionId)
            // Immediately fetch the new status to update the UI
            useMissionStore.getState().fetchMissionStatus(missionId)
          }
          break
          
        default:
          // No special action needed for 'chat' or other intents
          break
      }
    } catch (error) {
      console.error('Error handling agent action:', error)
      addToast({
        type: 'error',
        title: 'Action Error',
        message: 'There was an error processing the agent action. Please try again.',
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
        // Questions are generated and stored in the backend
        // The UI will show them through the research tabs
        addToast({
          type: 'info',
          title: 'Questions Generated',
          message: 'I\'ve generated initial research questions. You can review them in the research panel.',
          duration: 5000
        })
      }
    } catch (error) {
      console.error('Error generating questions:', error)
    }
  }

  const refineQuestions = async (_missionId: string, _feedback: string) => {
    // This would be handled by the backend through the MessengerAgent
    // The refined questions will be shown in the research tabs
    addToast({
      type: 'info',
      title: 'Refining Questions',
      message: 'I\'m updating the research questions based on your feedback.',
      duration: 3000
    })
  }

  const approveAndStartResearch = async (_missionId: string) => {
    try {
      // This would trigger the actual research execution
      addToast({
        type: 'success',
        title: 'Research Started',
        message: 'Great! I\'m starting the research process now. Monitor progress in the research panel.',
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


  // Show loading state when chat is being loaded
  if (chatLoading && !currentChat) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center max-w-md mx-auto p-8">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
            <Loader2 className="h-8 w-8 text-primary animate-spin" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-4">
            Loading Chat
          </h2>
          <p className="text-muted-foreground mb-6">
            Please wait while we load your conversation...
          </p>
        </div>
      </div>
    )
  }

  // Show welcome screen if no chat is selected or chat doesn't exist
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
            Welcome to MAESTRO
          </h2>
          <p className="text-muted-foreground mb-6">
            AI research assistant ready to help with analysis and insights.
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
            Start New Chat
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Chat Header */}
      <PanelHeader
        title={currentChat.title}
        subtitle={currentChat.messages.length === 0 
          ? 'Start the conversation' 
          : `${currentChat.messages.length} messages`
        }
        actions={
          <div className="flex items-center space-x-4">
            <PanelControls
              onTogglePanel={panelControls?.toggleRightPanel}
              isCollapsed={panelControls?.isRightPanelCollapsed}
              showToggle={true}
              toggleTooltip="Hide Research Panel"
            />
          </div>
        }
      />

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto space-y-4">
          {currentChat.messages.length === 0 ? (
            <div className="text-center py-8">
              <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-3">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-2">
                Ready to help!
              </h3>
              <p className="text-muted-foreground text-xs max-w-sm mx-auto">
                Ask questions, request analysis, or start a research mission.
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
                  {/* Avatar */}
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
                  
                  {/* Message Bubble */}
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
                          // Customize link rendering
                          a: ({node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" className={msg.role === 'user' ? "text-primary-foreground/80 hover:underline" : "text-primary hover:underline"} />,
                          // Reduced spacing for better chat bubble appearance
                          ul: ({node, ...props}) => <ul {...props} className="my-1 space-y-0.5" />,
                          ol: ({node, ...props}) => <ol {...props} className="my-1 space-y-0.5" />,
                          li: ({node, ...props}) => <li {...props} className="ml-4" />,
                          // Paragraphs
                          p: ({node, ...props}) => <p {...props} className="mb-1 last:mb-0 break-words leading-relaxed" />,
                          // Headings
                          h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-1 mt-2 first:mt-0" />,
                          h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-1 mt-1.5 first:mt-0" />,
                          h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-0.5 mt-1 first:mt-0" />,
                          h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                          // Blockquotes
                          blockquote: ({node, ...props}) => (
                            <blockquote 
                              {...props} 
                              className={`border-l-4 pl-4 my-1.5 italic ${
                                msg.role === 'user' ? 'border-primary-foreground/50' : 'border-border'
                              }`} 
                            />
                          ),
                          // Horizontal rules
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
                    <span className="text-xs text-text-tertiary">MAESTRO is thinking...</span>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Message Input */}
      <div className="bg-card border-t border-border p-4">
        <div className="max-w-4xl mx-auto">
          <Card>
            <CardContent className="p-4">
              <div className="flex flex-col">
                <div className="flex space-x-4">
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder={isChatDisabled ? "Mission is running..." : "Type your message or research request..."}
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
                      <label className="text-xs text-muted-foreground whitespace-nowrap">Document Group:</label>
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
                          <SelectValue placeholder="None" />
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
                    
                    <div className="flex items-center space-x-1.5">
                      <label className="text-xs text-muted-foreground whitespace-nowrap">Web Search:</label>
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
                        {useWebSearch ? 'On' : 'Off'}
                      </span>
                    </div>

                    {/* Mission Settings Button - Only show when there's a mission */}
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
                          Settings
                        </Button>
                      </div>
                    )}
                  </div>
                  
                  {!useWebSearch && !selectedGroupId && (
                    <div className="text-xs text-amber-600 bg-amber-500/10 px-2 py-1.5 rounded-md border border-amber-500/20 flex items-center space-x-1.5">
                      <span>⚠️</span>
                      <span>At least one information source must be enabled</span>
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
          
          <p className="text-xs text-muted-foreground mt-1.5 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Mission Settings Dialog */}
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
