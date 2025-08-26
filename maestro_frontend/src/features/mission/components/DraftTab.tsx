import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '../../../components/ui/card'
import { Button } from '../../../components/ui/button'
import { useMissionStore } from '../store'
import { useToast } from '../../../components/ui/toast'
import { FileText, RefreshCw, Copy, Edit3, X, Save, CheckCheck } from 'lucide-react'
import { apiClient } from '../../../config/api'

interface DraftTabProps {
  missionId: string
}

export const DraftTab: React.FC<DraftTabProps> = ({ missionId }) => {
  const { t } = useTranslation()
  const { activeMission, setMissionDraft, updateMissionReport } = useMissionStore()
  const { addToast } = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [editedReport, setEditedReport] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [wordCount, setWordCount] = useState(0)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success' | 'error'>('idle')

  const fetchDraft = useCallback(async (showLoading = true) => {
    if (!missionId) return
    if (showLoading) setIsLoading(true)
    try {
      const [draftResponse, reportResponse] = await Promise.allSettled([
        apiClient.get(`/api/missions/${missionId}/draft`),
        apiClient.get(`/api/missions/${missionId}/report`)
      ])
      
      if (reportResponse.status === 'fulfilled' && reportResponse.value.data?.final_report) {
        updateMissionReport(missionId, reportResponse.value.data.final_report)
      }
      
      if (draftResponse.status === 'fulfilled' && draftResponse.value.data?.draft) {
        setMissionDraft(missionId, draftResponse.value.data.draft)
      }
    } catch (error) {
      console.error(t('draftTab.failedToFetch'), error)
    } finally {
      if (showLoading) setIsLoading(false)
    }
  }, [missionId, setMissionDraft, updateMissionReport, t])

  useEffect(() => {
    if (!activeMission?.draft && !activeMission?.report) {
      fetchDraft()
    }
  }, [fetchDraft, activeMission?.draft, activeMission?.report])

  const getCurrentContent = () => {
    return activeMission?.report || activeMission?.draft || ''
  }

  useEffect(() => {
    const content = getCurrentContent()
    if (content && !isEditing) {
      setEditedReport(content)
    }
  }, [activeMission?.report, activeMission?.draft, isEditing])

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
      updateMissionReport(missionId, editedReport)
      setIsEditing(false)
      
      addToast({
        type: 'success',
        title: t('draftTab.draftUpdated'),
        message: t('draftTab.draftUpdatedSuccess')
      })
    } catch (error) {
      console.error('Failed to update report:', error)
      addToast({
        type: 'error',
        title: t('draftTab.updateFailed'),
        message: t('draftTab.updateFailedDescription')
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
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(content)
      } else {
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
      
      setCopyStatus('success')
      
      setTimeout(() => {
        setCopyStatus('idle')
      }, 2000)
      
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
      setCopyStatus('error')
      
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
        title: t('draftTab.draftRefreshed'),
        message: t('draftTab.draftRefreshedSuccess')
      })
    } catch (error) {
      console.error('Failed to refresh report:', error)
      addToast({
        type: 'error',
        title: t('draftTab.refreshFailed'),
        message: t('draftTab.refreshFailedDescription')
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleDownload = (format: 'md' | 'docx') => {
    if (format === 'md') {
      handleDownloadMarkdown();
    } else {
      handleDownloadWord();
    }
  };

  const extractTitleFromContent = (content: string): string => {
    const lines = content.split('\n')
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('# ')) {
        return trimmed.substring(2).trim().replace(/[^a-zA-Z0-9\s-]/g, '').replace(/\s+/g, '-')
      }
    }
    return `research-draft-${missionId.slice(0, 8)}`
  }

  const handleDownloadMarkdown = () => {
    const content = getCurrentContent()
    if (!content) {
      addToast({
        type: 'warning',
        title: t('draftTab.noContent'),
        message: t('draftTab.noContentToDownload')
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
      title: t('draftTab.draftDownloaded'),
      message: t('draftTab.downloadedAsMarkdown')
    })
  }

  const handleDownloadWord = async () => {
    const content = getCurrentContent();
    if (!content) {
      addToast({
        type: 'warning',
        title: t('draftTab.noContent'),
        message: t('draftTab.noContentToDownload'),
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
          title: t('draftTab.draftDownloaded'),
          message: t('draftTab.downloadedAsWord'),
        });
      } else {
        throw new Error(t('draftTab.invalidResponse'));
      }
    } catch (error: any) {
      console.error('Failed to download Word document:', error);
      
      let errorMessage = t('draftTab.downloadFailedDescription');
      if (error?.response) {
        if (error.response.status === 404) {
          errorMessage = t('draftTab.endpointNotFound');
        } else if (error.response.status === 500) {
          errorMessage = t('draftTab.serverError');
        }
      } else if (error?.request) {
        errorMessage = t('draftTab.networkError');
      }
      
      addToast({
        type: 'error',
        title: t('draftTab.downloadFailed'),
        message: errorMessage,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const formatMarkdown = (text: string) => {
    if (!text) return ''

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

      if (line.trim() === '') {
        flushParagraph()
        continue
      }

      if (line.match(/^[\*\-] /)) {
        flushParagraph()
        const listItem = line.substring(2)
        const processedListItem = listItem
          ?.replace(/&/g, '&')
          ?.replace(/</g, '<')
          ?.replace(/>/g, '>')
          ?.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
          ?.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
          ?.replace(/`([^`]+)`/g, '<code class="bg-secondary px-1 py-0.5 rounded text-sm font-mono">$1</code>')
        result.push(`<div class="mb-1 ml-4 text-sm">• ${processedListItem}</div>`)
        continue
      }

      let processedLine = line
        ?.replace(/&/g, '&')
        ?.replace(/</g, '<')
        ?.replace(/>/g, '>')
        ?.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
        ?.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
        ?.replace(/`([^`]+)`/g, '<code class="bg-secondary px-1 py-0.5 rounded text-sm font-mono">$1</code>')

      currentParagraph.push(processedLine)
    }

    flushParagraph()

    return result.join('\n')
  }

  const getStatusInfo = () => {
    if (!activeMission) return { color: 'gray', text: t('draftTab.noMission'), description: '' }
    
    switch (activeMission.status) {
      case 'pending':
        return { 
          color: 'yellow', 
          text: t('draftTab.planning'),
          description: t('draftTab.planningDescription')
        }
      case 'running':
        return { 
          color: 'blue', 
          text: t('draftTab.inProgress'),
          description: t('draftTab.inProgressDescription')
        }
      case 'completed':
        return { 
          color: 'green', 
          text: t('draftTab.completed'),
          description: t('draftTab.completedDescription')
        }
      case 'failed':
        return { 
          color: 'red', 
          text: t('draftTab.failed'),
          description: t('draftTab.failedDescription')
        }
      default:
        return { color: 'gray', text: t('draftTab.unknown'), description: '' }
    }
  }

  const statusInfo = getStatusInfo()

  return (
    <div className="h-full flex flex-col max-h-full overflow-hidden space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1">
            <FileText className="h-4 w-4 text-primary" />
            <h3 className="text-base font-semibold text-foreground">{t('draftTab.title')}</h3>
          </div>
          <div className="flex items-center space-x-1">
            <div className={`w-2 h-2 rounded-full bg-${statusInfo.color}-500`}></div>
            <span className="text-xs text-muted-foreground">{statusInfo.text}</span>
          </div>
          {wordCount > 0 && (
            <span className="text-xs text-muted-foreground">• {t('draftTab.wordCount', { count: wordCount.toLocaleString() })}</span>
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
                    ? t('draftTab.copying')
                    : copyStatus === 'success' 
                    ? t('draftTab.copied')
                    : copyStatus === 'error'
                    ? t('draftTab.copyFailed')
                    : t('draftTab.copyToClipboard')
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
                onClick={() => handleDownload('md')}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={isLoading}
              >
                {t('draftTab.md')}
              </Button>
              <Button
                onClick={() => handleDownload('docx')}
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={isLoading}
              >
                {t('draftTab.doc')}
              </Button>
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

      <Card className="flex-1 overflow-hidden">
        <CardContent className="p-0 h-full">
          {isEditing ? (
            <div className="h-full flex flex-col p-4 space-y-3">
              <div className="flex items-center justify-between flex-shrink-0">
                <h4 className="font-medium text-foreground">{t('draftTab.editTitle')}</h4>
                <div className="flex items-center space-x-2">
                  <Button
                    onClick={handleCancel}
                    variant="outline"
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <X className="h-4 w-4" />
                    {t('draftTab.cancel')}
                  </Button>
                  <Button
                    onClick={handleSave}
                    disabled={isLoading || !editedReport.trim()}
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <Save className="h-4 w-4" />
                    {isLoading ? t('draftTab.saving') : t('draftTab.save')}
                  </Button>
                </div>
              </div>
              <textarea
                value={editedReport}
                onChange={(e) => setEditedReport(e.target.value)}
                className="flex-1 w-full p-3 border border-border rounded-md font-mono text-sm resize-none focus:ring-2 focus:ring-primary focus:border-transparent min-h-0 bg-background"
                placeholder={t('draftTab.placeholder')}
              />
              <div className="text-sm text-muted-foreground flex-shrink-0">
                {t('draftTab.wordCount', { count: editedReport.trim().split(/\s+/).filter(word => word.length > 0).length })}
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
                    <p className="text-lg font-medium mb-2">{t('draftTab.noDraftAvailable')}</p>
                    <p className="text-sm">
                      {activeMission?.status === 'running' 
                        ? t('draftTab.draftGenerating')
                        : activeMission?.status === 'pending'
                          ? t('draftTab.draftAvailableLater')
                          : t('draftTab.startMission')
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
