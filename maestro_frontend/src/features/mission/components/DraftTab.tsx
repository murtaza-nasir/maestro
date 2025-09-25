import React, { useState, useEffect, useCallback } from 'react'
import { MathMarkdown } from '../../../components/markdown/MathMarkdown'
import { Card, CardContent } from '../../../components/ui/card'
import { Button } from '../../../components/ui/button'
import { useMissionStore } from '../store'
import { useChatStore } from '../../chat/store'
import { useToast } from '../../../components/ui/toast'
import { useWritingStore } from '../../writing/store'
import { useViewStore } from '../../../stores/viewStore'
import { FileText, RefreshCw, Copy, Edit3, X, Save, CheckCheck, ChevronLeft, ChevronRight, Clock, PenTool } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select'
// import {
//   DropdownMenu,
//   DropdownMenuContent,
//   DropdownMenuItem,
//   DropdownMenuTrigger,
// } from '../../../components/ui/dropdown-menu'
import { apiClient } from '../../../config/api'

interface DraftTabProps {
  missionId: string
}

interface ReportVersion {
  id: string
  version: number
  title?: string
  content: string
  is_current: boolean
  revision_notes?: string
  created_at: string
  updated_at?: string
}

export const DraftTab: React.FC<DraftTabProps> = ({ missionId }) => {
  const { setView } = useViewStore()
  const { activeMission, setMissionDraft, updateMissionReport, missions } = useMissionStore()
  const { activeChat } = useChatStore()
  const { createSession, selectSession } = useWritingStore()
  const { addToast } = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [editedReport, setEditedReport] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [wordCount, setWordCount] = useState(0)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success' | 'error'>('idle')
  const [reportVersions, setReportVersions] = useState<ReportVersion[]>([])
  const [currentVersion, setCurrentVersion] = useState<number>(1)
  const [selectedVersion, setSelectedVersion] = useState<number>(1)
  const [isTransitioning, setIsTransitioning] = useState(false)

  // Fetch available report versions
  const fetchReportVersions = useCallback(async () => {
    if (!missionId || activeMission?.status !== 'completed') return
    
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/reports`)
      if (response.data) {
        setReportVersions(response.data.reports || [])
        setCurrentVersion(response.data.current_version || 1)
        setSelectedVersion(response.data.current_version || 1)
      }
    } catch (error) {
      // Silently fail - versions might not be available for older missions
      console.log('Report versions not available')
    }
  }, [missionId, activeMission?.status])

  // Fetch specific version of the report
  const fetchReportVersion = useCallback(async (version: number) => {
    if (!missionId) return
    setIsLoading(true)
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/reports/${version}`)
      if (response.data && response.data.content) {
        // Update the displayed content but don't save it as the active mission report
        setEditedReport(response.data.content)
        setSelectedVersion(version)
      }
    } catch (error) {
      console.error('Failed to fetch report version:', error)
      addToast({
        type: 'error',
        title: 'Failed to load version',
        message: 'Could not load the selected report version'
      })
    } finally {
      setIsLoading(false)
    }
  }, [missionId, addToast])

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
      
      // Fetch versions if mission is completed
      if (activeMission?.status === 'completed') {
        fetchReportVersions()
      }
    } catch (error) {
      console.error('Failed to fetch mission content:', error)
    } finally {
      if (showLoading) setIsLoading(false)
    }
  }, [missionId, setMissionDraft, updateMissionReport, activeMission?.status, fetchReportVersions])

  // WebSocket updates are now handled by ResearchPanel
  // Initial fetch only
  useEffect(() => {
    if (!activeMission?.draft && !activeMission?.report) {
      fetchDraft()
    }
  }, [fetchDraft, activeMission?.draft, activeMission?.report])

  // Get the current content (prioritize selected version over default)
  const getCurrentContent = () => {
    // If we have a selected version that's different from current and we have the content
    if (selectedVersion !== currentVersion && editedReport && !isEditing) {
      return editedReport
    }
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
      // Save to backend using the new endpoint that doesn't update timestamps
      // The backend expects the content to be sent as plain text, not JSON
      await apiClient.put(`/api/missions/${missionId}/report`, JSON.stringify(editedReport), {
        headers: {
          'Content-Type': 'application/json'
        }
      })
      
      // Update local store
      updateMissionReport(missionId, editedReport)
      setIsEditing(false)
      
      addToast({
        type: 'success',
        title: 'Draft Updated',
        message: 'Research draft has been successfully saved.'
      })
    } catch (error) {
      console.error('Failed to update report:', error)
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: 'Failed to save the research draft. Please try again.'
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

  const handleTransitionToWriting = async () => {
    const content = getCurrentContent()
    if (!content) {
      addToast({
        type: 'warning',
        title: 'No Content',
        message: 'There is no draft content to continue with.'
      })
      return
    }

    setIsTransitioning(true)
    try {
      // Get the mission to find its document group
      const mission = missions.find(m => m.id === missionId)
      
      // Get the document group ID from the mission
      // First try to get the generated_document_group_id
      let documentGroupId = mission?.generated_document_group_id || null
      
      // If not found, fetch fresh status from backend to get the latest data
      if (!documentGroupId) {
        try {
          const statusResponse = await apiClient.get(`/api/missions/${missionId}/status`)
          documentGroupId = statusResponse.data.generated_document_group_id || null
        } catch (err) {
          console.error('Could not fetch mission status for document group:', err)
        }
      }
      
      // Extract title from the draft content
      const titleMatch = content.match(/^#\s+(.+)$/m)
      const draftTitle = titleMatch ? titleMatch[1].trim() : `Draft from Research ${missionId.slice(0, 8)}`
      
      // Create a new writing session with the document group if it exists
      const newSession = await createSession({
        name: `Writing: ${draftTitle}`,
        document_group_id: documentGroupId,
        web_search_enabled: true
      })
      
      // Get the draft (which will be created automatically if it doesn't exist)
      const draftResponse = await apiClient.get(`/api/writing/sessions/${newSession.id}/draft`)
      const draft = draftResponse.data
      
      // Update the draft with the research content
      await apiClient.put(`/api/writing/sessions/${newSession.id}/draft`, {
        title: draftTitle,
        content: content
      })
      
      // Explicitly select the session to ensure it stays selected
      await selectSession(newSession.id)
      
      // Switch to writing view
      setView('writing')
      
      addToast({
        type: 'success',
        title: 'Transitioned to Writing',
        message: 'Your research draft has been moved to the writing workspace.'
      })
    } catch (error) {
      console.error('Failed to transition to writing:', error)
      addToast({
        type: 'error',
        title: 'Transition Failed',
        message: 'Failed to move draft to writing workspace. Please try again.'
      })
    } finally {
      setIsTransitioning(false)
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
    // console.log('Download clicked:', format);
    // console.log('Current content available:', !!getCurrentContent());
    // console.log('Mission ID:', missionId);
    
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

  // formatMarkdown function removed - now using ReactMarkdown with KaTeX support
  /*
        flushTable()
        const number = numberedListMatch[1]
        const listItem = numberedListMatch[2]
        result.push(`<div class="mb-1 ml-4 text-sm"><span class="font-medium">${number}.</span> ${processInlineFormatting(listItem)}</div>`)
        continue
      }

      // Handle bullet lists
      if (line.match(/^[\*\-+] /)) {
        flushParagraph()
        flushTable()
        const listItem = line.substring(2)
        result.push(`<div class="mb-1 ml-4 text-sm">• ${processInlineFormatting(listItem)}</div>`)
        continue
      }

      // Regular text - add to current paragraph
      currentParagraph.push(processInlineFormatting(line))
    }

    // Flush any remaining content
    flushParagraph()
    flushTable()

    return result.join('\n')
  }
  */

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
    <div className="h-full flex flex-col">
      {/* Header with Status and Controls */}
      <div className="flex items-center justify-between p-2">
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
          
          {/* Version selector for completed missions with multiple versions */}
          {reportVersions.length > 1 && activeMission?.status === 'completed' && !isEditing && (
            <div className="flex items-center space-x-2 ml-2">
              <Clock className="h-3 w-3 text-muted-foreground" />
              <Select
                value={selectedVersion.toString()}
                onValueChange={(value) => fetchReportVersion(parseInt(value))}
                disabled={isLoading}
              >
                <SelectTrigger className="h-7 w-32 text-xs">
                  <SelectValue placeholder="Select version" />
                </SelectTrigger>
                <SelectContent>
                  {reportVersions.map((version) => (
                    <SelectItem key={version.id} value={version.version.toString()}>
                      <div className="flex items-center justify-between w-full">
                        <span>Version {version.version}</span>
                        {version.is_current && (
                          <span className="text-xs text-muted-foreground ml-2">(current)</span>
                        )}
                      </div>
                      {version.revision_notes && (
                        <div className="text-xs text-muted-foreground mt-1">
                          {version.revision_notes.substring(0, 50)}...
                        </div>
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
                  // console.log('DIRECT MARKDOWN TEST BUTTON CLICKED');
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
                  // console.log('DIRECT WORD TEST BUTTON CLICKED');
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
                    // console.log('MARKDOWN CLICK HANDLER CALLED');
                    handleDownload('md');
                  }}>
                    <FileText className="mr-2 h-4 w-4" />
                    Download as Markdown
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => {
                    // console.log('WORD CLICK HANDLER CALLED');
                    handleDownload('docx');
                  }}>
                    <FileText className="mr-2 h-4 w-4" />
                    Download as Word
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              */}
              {/* Show Continue Writing button for completed missions, Edit for others */}
              {activeMission?.status === 'completed' ? (
                <Button
                  onClick={handleTransitionToWriting}
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs flex items-center gap-1"
                  disabled={isTransitioning}
                >
                  {isTransitioning ? (
                    <>
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      <span>Creating...</span>
                    </>
                  ) : (
                    <>
                      <PenTool className="h-3 w-3" />
                      <span>Write</span>
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  onClick={handleEdit}
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs"
                >
                  <Edit3 className="h-3 w-3" />
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Draft Content - Card Layout */}
      <Card className="flex-1 overflow-hidden mx-2 mb-2">
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
                <div className="flex-1 overflow-y-auto p-4">
                    <div className="prose prose-sm max-w-none text-foreground" style={{overflowWrap: 'anywhere', wordBreak: 'break-word'}}>
                      <MathMarkdown
                        content={getCurrentContent() || ''}
                        className="prose prose-sm max-w-none"
                        components={{
                          a: ({node, ...props}) => (
                            <a 
                              {...props} 
                              target="_blank" 
                              rel="noopener noreferrer" 
                              className="text-primary hover:underline"
                            />
                          ),
                          code: ({node, className, children, ...props}) => {
                            const match = /language-(\w+)/.exec(className || '')
                            const isInline = !match && !String(children).includes('\n')
                            
                            if (isInline) {
                              return (
                                <code 
                                  {...props}
                                  className="inline-block bg-secondary px-1 py-0.5 rounded text-xs font-mono"
                                >
                                  {children}
                                </code>
                              )
                            }
                            
                            return (
                              <code 
                                {...props}
                                className="block bg-secondary p-2 rounded text-sm overflow-x-auto max-w-full font-mono"
                              >
                                {children}
                              </code>
                            )
                          },
                          ul: ({node, ...props}) => <ul {...props} className="my-2 ml-4" />,
                          ol: ({node, ...props}) => <ol {...props} className="my-2 ml-4" />,
                          li: ({node, ...props}) => <li {...props} className="my-1" />,
                          p: ({node, ...props}) => <p {...props} className="my-2" />,
                          h1: ({node, ...props}) => <h1 {...props} className="text-xl font-bold my-3 text-primary" />,
                          h2: ({node, ...props}) => <h2 {...props} className="text-lg font-semibold my-2 text-primary" />,
                          h3: ({node, ...props}) => <h3 {...props} className="text-base font-semibold my-2 text-primary" />,
                          h4: ({node, ...props}) => <h4 {...props} className="text-sm font-medium my-2 text-primary" />,
                          h5: ({node, ...props}) => <h5 {...props} className="text-sm font-medium my-2 text-primary" />,
                          h6: ({node, ...props}) => <h6 {...props} className="text-sm font-medium my-2 text-primary" />,
                          blockquote: ({node, ...props}) => (
                            <blockquote 
                              {...props} 
                              className="border-l-4 border-primary pl-4 my-2 italic text-muted-foreground"
                            />
                          ),
                          table: ({node, ...props}) => (
                            <table {...props} className="border-collapse border border-border my-2" />
                          ),
                          th: ({node, ...props}) => (
                            <th {...props} className="border border-border px-2 py-1 bg-muted font-semibold text-foreground" />
                          ),
                          td: ({node, ...props}) => (
                            <td {...props} className="border border-border px-2 py-1" />
                          ),
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
