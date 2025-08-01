import React, { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '../../../components/ui/card'
import { Button } from '../../../components/ui/button'
import { useMissionStore } from '../store'
import { useToast } from '../../../components/ui/toast'
import { FileText, RefreshCw, Copy, Edit3, X, Save, CheckCheck } from 'lucide-react'
// import {
//   DropdownMenu,
//   DropdownMenuContent,
//   DropdownMenuItem,
//   DropdownMenuTrigger,
// } from '../../../components/ui/dropdown-menu'
import { apiClient } from '../../../config/api'
import { useMissionWebSocket } from '../../../services/websocket'

interface DraftTabProps {
  missionId: string
}

export const DraftTab: React.FC<DraftTabProps> = ({ missionId }) => {
  const { activeMission, setMissionDraft, updateMissionReport } = useMissionStore()
  const { addToast } = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [editedReport, setEditedReport] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [wordCount, setWordCount] = useState(0)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success' | 'error'>('idle')

  // WebSocket connection for real-time draft updates
  const { isConnected, subscribe } = useMissionWebSocket(missionId)

  const fetchDraft = useCallback(async (showLoading = true) => {
    if (!missionId) return
    if (showLoading) setIsLoading(true)
    try {
      // Fetch both draft and report to get the most complete content
      const [draftResponse, reportResponse] = await Promise.allSettled([
        apiClient.get(`/api/missions/${missionId}/draft`),
        apiClient.get(`/api/missions/${missionId}/report`)
      ])
      
      // Handle final report (completed missions)
      if (reportResponse.status === 'fulfilled' && reportResponse.value.data?.final_report) {
        updateMissionReport(missionId, reportResponse.value.data.final_report)
      }
      
      // Handle draft content (work in progress)
      if (draftResponse.status === 'fulfilled' && draftResponse.value.data?.draft) {
        setMissionDraft(missionId, draftResponse.value.data.draft)
      }
    } catch (error) {
      console.error('Failed to fetch mission content:', error)
    } finally {
      if (showLoading) setIsLoading(false)
    }
  }, [missionId, setMissionDraft, updateMissionReport])

  // Handle WebSocket draft updates
  useEffect(() => {
    if (!isConnected) return

    const unsubscribe = subscribe('draft_update', (message: any) => {
      if (import.meta.env.DEV) {
        console.log('Draft update received')
      }
      
      if (message.mission_id === missionId && message.data) {
        if (message.action === 'draft') {
          setMissionDraft(missionId, message.data)
        } else if (message.action === 'report') {
          updateMissionReport(missionId, message.data)
        }
      }
    })

    return unsubscribe
  }, [isConnected, subscribe, missionId, setMissionDraft, updateMissionReport])

  // Initial fetch only - rely on ResearchPanel's WebSocket for updates
  useEffect(() => {
    if (!activeMission?.draft && !activeMission?.report) {
      fetchDraft()
    }
  }, [fetchDraft, activeMission?.draft, activeMission?.report])

  // Get the current content (prioritize report over draft)
  const getCurrentContent = () => {
    return activeMission?.report || activeMission?.draft || ''
  }

  // Update edited report when mission content changes
  useEffect(() => {
    const content = getCurrentContent()
    if (content && !isEditing) {
      setEditedReport(content)
    }
  }, [activeMission?.report, activeMission?.draft, isEditing])

  // Calculate word count
  useEffect(() => {
    const text = isEditing ? editedReport : getCurrentContent()
    const words = text.trim().split(/\s+/).filter(word => word.length > 0)
    setWordCount(words.length)
  }, [editedReport, activeMission?.report, activeMission?.draft, isEditing])

  const handleEdit = () => {
    setEditedReport(getCurrentContent())
    setIsEditing(true)
  }

  const handleSave = async () => {
    if (!missionId || !editedReport.trim()) return

    setIsLoading(true)
    try {
      // TODO: Implement API call to update report
      // await api.put(`/api/missions/${missionId}/report`, { report: editedReport })
      
      updateMissionReport(missionId, editedReport)
      setIsEditing(false)
      
      addToast({
        type: 'success',
        title: 'Draft Updated',
        message: 'Research draft has been successfully updated.'
      })
    } catch (error) {
      console.error('Failed to update report:', error)
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: 'Failed to update the research draft. Please try again.'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    setEditedReport(getCurrentContent())
    setIsEditing(false)
  }

  const handleCopy = async () => {
    const content = getCurrentContent()
    if (!content) return

    setCopyStatus('copying')

    try {
      // Check if clipboard API is available
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(content)
      } else {
        // Fallback for older browsers or insecure contexts
        const textArea = document.createElement('textarea')
        textArea.value = content
        textArea.style.position = 'fixed'
        textArea.style.left = '-999999px'
        textArea.style.top = '-999999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        
        const successful = document.execCommand('copy')
        document.body.removeChild(textArea)
        
        if (!successful) {
          throw new Error('Legacy copy method failed')
        }
      }
      
      // Show success feedback
      setCopyStatus('success')
      
      // Reset to idle after 2 seconds
      setTimeout(() => {
        setCopyStatus('idle')
      }, 2000)
      
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
      setCopyStatus('error')
      
      // Reset to idle after 3 seconds
      setTimeout(() => {
        setCopyStatus('idle')
      }, 3000)
    }
  }

  const handleRefresh = async () => {
    if (!missionId) return
    
    setIsLoading(true)
    try {
      await fetchDraft()
      addToast({
        type: 'success',
        title: 'Draft Refreshed',
        message: 'Latest draft has been loaded.'
      })
    } catch (error) {
      console.error('Failed to refresh report:', error)
      addToast({
        type: 'error',
        title: 'Refresh Failed',
        message: 'Failed to refresh the draft. Please try again.'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleDownload = (format: 'md' | 'docx') => {
    console.log('Download clicked:', format);
    console.log('Current content available:', !!getCurrentContent());
    console.log('Mission ID:', missionId);
    
    if (format === 'md') {
      handleDownloadMarkdown();
    } else {
      handleDownloadWord();
    }
  };

  const extractTitleFromContent = (content: string): string => {
    // Try to extract the first heading from the content
    const lines = content.split('\n')
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('# ')) {
        // Remove the # and clean up the title
        return trimmed.substring(2).trim().replace(/[^a-zA-Z0-9\s-]/g, '').replace(/\s+/g, '-')
      }
    }
    // Fallback to mission ID if no title found
    return `research-draft-${missionId.slice(0, 8)}`
  }

  const handleDownloadMarkdown = () => {
    const content = getCurrentContent()
    if (!content) {
      addToast({
        type: 'warning',
        title: 'No Content',
        message: 'There is no draft content to download.'
      })
      return
    }

    const title = extractTitleFromContent(content)
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    addToast({
      type: 'success',
      title: 'Draft Downloaded',
      message: 'Research draft has been downloaded as Markdown.'
    })
  }

  const handleDownloadWord = async () => {
    const content = getCurrentContent();
    if (!content) {
      addToast({
        type: 'warning',
        title: 'No Content',
        message: 'There is no draft content to download.',
      });
      return;
    }
  
    setIsLoading(true);
    try {
      const title = extractTitleFromContent(content)
      const response = await apiClient.post(
        `/api/missions/${missionId}/report/docx`,
        { 
          markdown_content: content,
          filename: title
        },
        { 
          responseType: 'blob',
          headers: {
            'Content-Type': 'application/json'
          }
        }
      );
  
      // Check if the response is actually a blob
      if (response.data instanceof Blob) {
        const url = URL.createObjectURL(response.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}.docx`;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        addToast({
          type: 'success',
          title: 'Draft Downloaded',
          message: 'Research draft has been downloaded as a Word document.',
        });
      } else {
        throw new Error('Invalid response format');
      }
    } catch (error: any) {
      console.error('Failed to download Word document:', error);
      
      // More detailed error handling
      let errorMessage = 'Failed to download the draft as a Word document. Please try again.';
      if (error?.response) {
        if (error.response.status === 404) {
          errorMessage = 'Download endpoint not found. Please contact support.';
        } else if (error.response.status === 500) {
          errorMessage = 'Server error occurred while generating the document.';
        }
      } else if (error?.request) {
        errorMessage = 'Network error. Please check your connection and try again.';
      }
      
      addToast({
        type: 'error',
        title: 'Download Failed',
        message: errorMessage,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const formatMarkdown = (text: string) => {
    if (!text) return ''

    // Split text into lines for processing
    const lines = text.split('\n')
    const result: string[] = []
    let inCodeBlock = false
    let currentParagraph: string[] = []

    const flushParagraph = () => {
      if (currentParagraph.length > 0) {
        const paragraphText = currentParagraph.join('<br>')
        if (paragraphText.trim()) {
          result.push(`<p class="mb-3 text-sm text-foreground">${paragraphText}</p>`)
        }
        currentParagraph = []
      }
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      
      // Handle code blocks
      if (line.startsWith('```')) {
        flushParagraph()
        if (!inCodeBlock) {
          inCodeBlock = true
          result.push('<pre class="bg-secondary p-3 rounded text-sm font-mono mb-4 overflow-x-auto">')
        } else {
          inCodeBlock = false
          result.push('</pre>')
        }
        continue
      }

      if (inCodeBlock) {
        result.push(line?.replace(/&/g, '&')?.replace(/</g, '<')?.replace(/>/g, '>') || line)
        continue
      }

      // Handle headers (including 4th and 5th level headings)
      if (line.startsWith('##### ')) {
        flushParagraph()
        result.push(`<h5 class="text-sm font-medium mb-2 text-muted-foreground">${line.substring(6)}</h5>`)
        continue
      }
      if (line.startsWith('#### ')) {
        flushParagraph()
        result.push(`<h4 class="text-sm font-medium mb-2 text-muted-foreground">${line.substring(5)}</h4>`)
        continue
      }
      if (line.startsWith('### ')) {
        flushParagraph()
        result.push(`<h3 class="text-base font-medium mb-2 text-foreground">${line.substring(4)}</h3>`)
        continue
      }
      if (line.startsWith('## ')) {
        flushParagraph()
        result.push(`<h2 class="text-lg font-semibold mb-3 text-foreground">${line.substring(3)}</h2>`)
        continue
      }
      if (line.startsWith('# ')) {
        flushParagraph()
        result.push(`<h1 class="text-xl font-bold mb-4 text-foreground">${line.substring(2)}</h1>`)
        continue
      }

      // Handle empty lines
      if (line.trim() === '') {
        flushParagraph()
        continue
      }

      // Handle list items
      if (line.match(/^[\*\-] /)) {
        flushParagraph()
        const listItem = line.substring(2)
        result.push(`<div class="mb-1 ml-4 text-sm">• ${listItem}</div>`)
        continue
      }

      // Regular text - add to current paragraph
      let processedLine = line
        ?.replace(/&/g, '&')
        ?.replace(/</g, '<')
        ?.replace(/>/g, '>')
        ?.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
        ?.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
        ?.replace(/`([^`]+)`/g, '<code class="bg-secondary px-1 py-0.5 rounded text-sm font-mono">$1</code>')

      currentParagraph.push(processedLine)
    }

    // Flush any remaining paragraph
    flushParagraph()

    return result.join('\n')
  }

  const getStatusInfo = () => {
    if (!activeMission) return { color: 'gray', text: 'No Mission', description: '' }
    
    switch (activeMission.status) {
      case 'pending':
        return { 
          color: 'yellow', 
          text: 'Planning', 
          description: 'Draft will be generated after research phase'
        }
      case 'running':
        return { 
          color: 'blue', 
          text: 'In Progress', 
          description: 'Draft is being written and updated in real-time'
        }
      case 'completed':
        return { 
          color: 'green', 
          text: 'Completed', 
          description: 'Final research report is ready'
        }
      case 'failed':
        return { 
          color: 'red', 
          text: 'Failed', 
          description: 'Mission encountered an error'
        }
      default:
        return { color: 'gray', text: 'Unknown', description: '' }
    }
  }

  const statusInfo = getStatusInfo()

  return (
    <div className="h-full flex flex-col max-h-full overflow-hidden space-y-2">
      {/* Header with Status and Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1">
            <FileText className="h-4 w-4 text-primary" />
            <h3 className="text-base font-semibold text-foreground">Research Draft</h3>
          </div>
          <div className="flex items-center space-x-1">
            <div className={`w-2 h-2 rounded-full bg-${statusInfo.color}-500`}></div>
            <span className="text-xs text-muted-foreground">{statusInfo.text}</span>
          </div>
          {wordCount > 0 && (
            <span className="text-xs text-muted-foreground">• {wordCount.toLocaleString()} words</span>
          )}
        </div>
        
        <div className="flex items-center space-x-1">
          {!isEditing && getCurrentContent() && (
            <>
              <Button
                onClick={handleCopy}
                variant="outline"
                size="sm"
                disabled={!getCurrentContent() || copyStatus === 'copying'}
                className={`h-7 px-2 text-xs transition-colors duration-200 ${
                  copyStatus === 'success' 
                    ? 'text-green-500 hover:text-green-600 hover:bg-green-500/10 border-green-500/20' 
                    : copyStatus === 'error'
                    ? 'text-destructive hover:text-destructive/80 hover:bg-destructive/10 border-destructive/20'
                    : ''
                }`}
                title={
                  copyStatus === 'copying' 
                    ? 'Copying...' 
                    : copyStatus === 'success' 
                    ? 'Copied!' 
                    : copyStatus === 'error'
                    ? 'Copy failed'
                    : 'Copy to clipboard'
                }
              >
                {copyStatus === 'success' ? (
                  <CheckCheck className="h-3 w-3" />
                ) : copyStatus === 'error' ? (
                  <X className="h-3 w-3" />
                ) : (
                  <Copy className={`h-3 w-3 ${copyStatus === 'copying' ? 'animate-pulse' : ''}`} />
                )}
              </Button>
              <Button
                onClick={handleRefresh}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={isLoading}
              >
                <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
              <Button
                onClick={() => {
                  console.log('DIRECT MARKDOWN TEST BUTTON CLICKED');
                  handleDownload('md');
                }}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={isLoading}
              >
                MD
              </Button>
              <Button
                onClick={() => {
                  console.log('DIRECT WORD TEST BUTTON CLICKED');
                  handleDownload('docx');
                }}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={isLoading}
              >
                DOC
              </Button>
              {/* Dropdown menu temporarily commented out - keeping direct MD and DOC buttons */}
              {/*
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    disabled={isLoading}
                  >
                    <Download className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {
                    console.log('MARKDOWN CLICK HANDLER CALLED');
                    handleDownload('md');
                  }}>
                    <FileText className="mr-2 h-4 w-4" />
                    Download as Markdown
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => {
                    console.log('WORD CLICK HANDLER CALLED');
                    handleDownload('docx');
                  }}>
                    <FileText className="mr-2 h-4 w-4" />
                    Download as Word
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              */}
              <Button
                onClick={handleEdit}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
              >
                <Edit3 className="h-3 w-3" />
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Draft Content - Card Layout */}
      <Card className="flex-1 overflow-hidden">
        <CardContent className="p-0 h-full">
          {isEditing ? (
            <div className="h-full flex flex-col p-4 space-y-3">
              <div className="flex items-center justify-between flex-shrink-0">
                <h4 className="font-medium text-foreground">Edit Research Draft</h4>
                <div className="flex items-center space-x-2">
                  <Button
                    onClick={handleCancel}
                    variant="outline"
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <X className="h-4 w-4" />
                    Cancel
                  </Button>
                  <Button
                    onClick={handleSave}
                    disabled={isLoading || !editedReport.trim()}
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <Save className="h-4 w-4" />
                    {isLoading ? 'Saving...' : 'Save'}
                  </Button>
                </div>
              </div>
              <textarea
                value={editedReport}
                onChange={(e) => setEditedReport(e.target.value)}
                className="flex-1 w-full p-3 border border-border rounded-md font-mono text-sm resize-none focus:ring-2 focus:ring-primary focus:border-transparent min-h-0 bg-background"
                placeholder="Enter your research draft here..."
              />
              <div className="text-sm text-muted-foreground flex-shrink-0">
                {editedReport.trim().split(/\s+/).filter(word => word.length > 0).length} words
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col">
              {getCurrentContent() ? (
                <div className="flex-1 overflow-hidden">
                  <div className="h-full overflow-y-auto p-4">
                    <div 
                      className="text-foreground"
                      dangerouslySetInnerHTML={{ 
                        __html: formatMarkdown(getCurrentContent())
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                    <p className="text-lg font-medium mb-2">No Draft Available</p>
                    <p className="text-sm">
                      {activeMission?.status === 'running' 
                        ? 'The research draft is being generated...'
                        : activeMission?.status === 'pending'
                          ? 'Draft will be available after the research phase begins.'
                          : 'Start a research mission to see the draft here.'
                      }
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
