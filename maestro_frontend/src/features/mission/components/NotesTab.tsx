import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { Card, CardContent } from '../../../components/ui/card'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { useMissionStore, type Note } from '../store'
import { useToast } from '../../../components/ui/toast'
import { Search, BookOpen, Filter, Calendar, ExternalLink, FileText } from 'lucide-react'
import { apiClient } from '../../../config/api'
import { formatFullDateTime } from '../../../utils/timezone'

interface NotesTabProps {
  missionId: string
}

export const NotesTab: React.FC<NotesTabProps> = ({ missionId }) => {
  const { t } = useTranslation();
  const { activeMission, setMissionNotes } = useMissionStore()
  const { addToast } = useToast()
  const [notes, setNotes] = useState<Note[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'web' | 'documents'>('all')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMoreNotes, setHasMoreNotes] = useState(true)
  const [totalNotesCount, setTotalNotesCount] = useState(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const lastScrollPosition = useRef<number>(0)
  const initialLoadDone = useRef(false)
  const previousMissionId = useRef<string | null>(null)

  const preserveScrollPosition = useCallback(() => {
    if (scrollContainerRef.current) {
      lastScrollPosition.current = scrollContainerRef.current.scrollTop
    }
  }, [])

  const restoreScrollPosition = useCallback(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = lastScrollPosition.current
    }
  }, [])

  const fetchNotesAPI = useCallback(async (limit: number, offset: number) => {
    const response = await apiClient.get(`/api/missions/${missionId}/notes?limit=${limit}&offset=${offset}`)
    return response.data
  }, [missionId])

  const loadInitialNotes = useCallback(async () => {
    if (previousMissionId.current !== missionId) {
      initialLoadDone.current = false
      previousMissionId.current = missionId
      setNotes([])
      setTotalNotesCount(0)
    }
    
    if (initialLoadDone.current) return
    
    setIsLoading(true)
    try {
      const data = await fetchNotesAPI(50, 0)
      const newNotes = data.notes || data
      const total = data.total || newNotes.length
      const hasMore = data.has_more !== undefined ? data.has_more : false

      setNotes(newNotes)
      setMissionNotes(missionId, newNotes)
      setTotalNotesCount(total)
      setHasMoreNotes(hasMore)
      initialLoadDone.current = true
    } catch (error) {
      console.error(t('notesTab.failedToFetch'), error)
    } finally {
      setIsLoading(false)
    }
  }, [missionId, setMissionNotes, fetchNotesAPI, t])

  const loadMoreNotes = useCallback(async () => {
    if (!hasMoreNotes || isLoadingMore) return
    
    setIsLoadingMore(true)
    try {
      const currentLength = notes.length
      const data = await fetchNotesAPI(50, currentLength)
      const newNotes = data.notes || data
      const total = data.total || (currentLength + newNotes.length)
      const hasMore = data.has_more !== undefined ? data.has_more : false

      setNotes(prev => {
        const updated = [...prev, ...newNotes]
        setMissionNotes(missionId, updated)
        return updated
      })
      setTotalNotesCount(total)
      setHasMoreNotes(hasMore)
    } catch (error) {
      console.error(t('notesTab.failedToLoadMore'), error)
    } finally {
      setIsLoadingMore(false)
    }
  }, [hasMoreNotes, isLoadingMore, notes.length, missionId, setMissionNotes, fetchNotesAPI, t])

  const loadAllNotes = useCallback(async () => {
    if (!hasMoreNotes) return
    
    setIsLoading(true)
    try {
      const data = await fetchNotesAPI(1000, 0)
      const allNotes = data.notes || data
      const total = data.total || allNotes.length

      setNotes(allNotes)
      setMissionNotes(missionId, allNotes)
      setTotalNotesCount(total)
      setHasMoreNotes(false)
    } catch (error) {
      console.error(t('notesTab.failedToLoadAll'), error)
    } finally {
      setIsLoading(false)
    }
  }, [hasMoreNotes, missionId, setMissionNotes, fetchNotesAPI, t])

  useEffect(() => {
    loadInitialNotes()
  }, [loadInitialNotes])

  useEffect(() => {
    if (activeMission?.notes && activeMission.id === missionId && initialLoadDone.current) {
      const storeNotes = activeMission.notes
      
      if (previousMissionId.current === missionId) {
        const currentLastNoteId = notes.length > 0 ? notes[notes.length - 1].note_id : null
        const storeLastNoteId = storeNotes.length > 0 ? storeNotes[storeNotes.length - 1].note_id : null
        
        if (storeNotes.length !== notes.length || currentLastNoteId !== storeLastNoteId) {
          preserveScrollPosition()
          
          const newNotesCount = Math.max(0, storeNotes.length - notes.length)
          if (newNotesCount >= 5) {
            setTimeout(() => {
              addToast({
                type: 'info',
                title: t('notesTab.newNotes'),
                message: newNotesCount > 1 ? t('notesTab.newNotesAdded', { count: newNotesCount }) : t('notesTab.newNoteAdded', { count: newNotesCount }),
              })
            }, 500)
          }
          
          setNotes(storeNotes)
          setTotalNotesCount(storeNotes.length)
          
          setTimeout(restoreScrollPosition, 50)
        }
      } else {
        if (storeNotes.length > 0) {
          setNotes(storeNotes)
          setTotalNotesCount(storeNotes.length)
        }
      }
    }
  }, [activeMission?.notes, activeMission?.id, missionId, notes.length, preserveScrollPosition, restoreScrollPosition, addToast, t])

  useEffect(() => {
    if (activeMission?.notes && activeMission.id === missionId && !initialLoadDone.current) {
      if (activeMission.notes.length > 0) {
        setNotes(activeMission.notes)
        setTotalNotesCount(activeMission.notes.length)
      }
    }
  }, [activeMission?.notes, activeMission?.id, missionId])

  const filteredNotes = notes.filter(note => {
    const matchesSearch = searchTerm === '' || 
      note.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (note.source && note.source.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (note.url && note.url.toLowerCase().includes(searchTerm.toLowerCase()))

    const matchesFilter = selectedFilter === 'all' || 
      (selectedFilter === 'web' && note.url) ||
      (selectedFilter === 'documents' && note.source && !note.url)

    return matchesSearch && matchesFilter
  })

  const handleExportNotes = () => {
    const notesText = filteredNotes.map(note => {
      const sourceInfo = note.source || t('notesTab.unknownSource')
      const urlInfo = note.url || ''
      return `[${formatFullDateTime(note.timestamp)}] (${sourceInfo})\n${note.content}\n${urlInfo ? `URL: ${urlInfo}` : ''}\n---\n`
    }).join('\n')

    const blob = new Blob([notesText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mission-notes-${missionId.slice(0, 8)}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    addToast({
      type: 'success',
      title: t('notesTab.notesExported'),
      message: t('notesTab.notesExportedSuccess')
    })
  }

  const getFilterCount = (filter: 'all' | 'web' | 'documents') => {
    if (filter === 'all') return totalNotesCount || notes.length
    if (filter === 'web') return notes.filter(note => note.url).length
    if (filter === 'documents') return notes.filter(note => note.source && !note.url).length
    return 0
  }

  return (
    <div className="flex flex-col h-full max-h-full overflow-hidden space-y-2">
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h3 className="text-base font-semibold text-foreground">{t('notesTab.title')}</h3>
          <span className="text-xs text-muted-foreground">{t('notesTab.notesCount', { count: filteredNotes.length })}</span>
        </div>
        
        <Button
          onClick={handleExportNotes}
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs"
          disabled={filteredNotes.length === 0}
        >
          <FileText className="h-3 w-3" />
        </Button>
      </div>

      <Card className="flex-shrink-0">
        <CardContent className="p-2">
          <div className="flex flex-col gap-2">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1 relative">
                <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder={t('notesTab.searchPlaceholder')}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-7 h-7 text-xs bg-background"
                />
              </div>

              <div className="flex items-center space-x-1">
                <Filter className="h-3 w-3 text-muted-foreground" />
                <div className="flex space-x-1">
                  {(['all', 'web', 'documents'] as const).map((filter) => (
                    <Button
                      key={filter}
                      onClick={() => setSelectedFilter(filter)}
                      variant={selectedFilter === filter ? 'default' : 'outline'}
                      size="sm"
                      className="capitalize h-7 px-2 text-xs"
                    >
                      {t(`notesTab.${filter}`)} ({getFilterCount(filter)})
                    </Button>
                  ))}
                </div>
              </div>
            </div>

            {(hasMoreNotes || notes.length < totalNotesCount) && (
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {t('notesTab.showingNotes', { count: notes.length, total: totalNotesCount })}
                </span>
                <div className="flex space-x-2">
                  <Button
                    onClick={loadMoreNotes}
                    variant="outline"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={isLoadingMore || !hasMoreNotes}
                  >
                    {isLoadingMore ? t('notesTab.loading') : t('notesTab.loadMore')}
                  </Button>
                  <Button
                    onClick={loadAllNotes}
                    variant="outline"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    disabled={isLoading || !hasMoreNotes}
                  >
                    {t('notesTab.loadAll')}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto space-y-2 min-h-0">
        {isLoading ? (
          <Card>
            <CardContent className="p-4 text-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary mx-auto mb-2"></div>
              <p className="text-xs text-muted-foreground">{t('notesTab.loadingNotes')}</p>
            </CardContent>
          </Card>
        ) : filteredNotes.length > 0 ? (
          filteredNotes.map((note) => (
            <Card key={note.note_id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-3">
                <div className="space-y-2">
                  <div className="border-b border-border pb-2 mb-2">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-1 text-xs text-muted-foreground mb-1">
                          <Calendar className="h-3 w-3" />
                          <span>{formatFullDateTime(note.timestamp)}</span>
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium ${
                            note.url ? 'bg-primary/10 text-primary' :
                            note.source ? 'bg-green-500/10 text-green-500' :
                            'bg-secondary text-muted-foreground'
                          }`}>
                            {note.url ? `🌐 ${t('notesTab.webSource')}` :
                             note.source ? `📄 ${t('notesTab.docSource')}` :
                             `🔧 ${t('notesTab.intSource')}`}
                          </span>
                        </div>
                        {note.source && (
                          <h4 className="font-medium text-foreground text-xs mb-1 break-words overflow-wrap-anywhere">{note.source}</h4>
                        )}
                      </div>
                      {note.url && (
                        <Button
                          onClick={() => window.open(note.url, '_blank')}
                          variant="outline"
                          size="sm"
                          className="h-6 px-1.5 text-xs ml-2"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="text-foreground leading-relaxed overflow-hidden">
                    <div className="prose prose-sm max-w-none text-xs break-words overflow-wrap-anywhere">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          a: ({node, ...props}) => (
                            <a 
                              {...props} 
                              target="_blank" 
                              rel="noopener noreferrer" 
                              className="text-primary hover:underline break-all"
                            />
                          ),
                          code: ({node, ...props}) => {
                            const { inline, ...restProps } = props as any;
                            return inline ? (
                              <code 
                                {...restProps} 
                                className="bg-secondary px-1 py-0.5 rounded text-xs break-all"
                              />
                            ) : (
                              <code 
                                {...restProps} 
                                className="block bg-secondary p-2 rounded text-xs break-all overflow-x-auto"
                              />
                            );
                          },
                          ul: ({node, ...props}) => <ul {...props} className="my-1 ml-4" />,
                          ol: ({node, ...props}) => <ol {...props} className="my-1 ml-4" />,
                          li: ({node, ...props}) => <li {...props} className="my-0.5" />,
                          p: ({node, ...props}) => <p {...props} className="my-1" />,
                          h1: ({node, ...props}) => <h1 {...props} className="text-sm font-bold my-1" />,
                          h2: ({node, ...props}) => <h2 {...props} className="text-sm font-semibold my-1" />,
                          h3: ({node, ...props}) => <h3 {...props} className="text-xs font-semibold my-1" />,
                          h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium my-1" />,
                          h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium my-1" />,
                          h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium my-1" />,
                          blockquote: ({node, ...props}) => (
                            <blockquote 
                              {...props} 
                              className="border-l-2 border-border pl-2 my-1 italic text-muted-foreground"
                            />
                          ),
                          table: ({node, ...props}) => (
                            <table {...props} className="border-collapse border border-border text-xs my-1" />
                          ),
                          th: ({node, ...props}) => (
                            <th {...props} className="border border-border px-1 py-0.5 bg-secondary font-semibold" />
                          ),
                          td: ({node, ...props}) => (
                            <td {...props} className="border border-border px-1 py-0.5" />
                          ),
                        }}
                      >
                        {note.content || ''}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {note.tags && note.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {note.tags.map((tag: string) => (
                        <span
                          key={tag}
                          className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-500"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <Card>
            <CardContent className="p-4 text-center text-muted-foreground">
              <BookOpen className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              <p className="text-sm font-medium mb-1">
                {searchTerm || selectedFilter !== 'all' ? t('notesTab.noMatchingNotes') : t('notesTab.noNotesAvailable')}
              </p>
              <p className="text-xs">
                {searchTerm || selectedFilter !== 'all' 
                  ? t('notesTab.adjustFilters')
                  : activeMission?.status === 'running' 
                    ? t('notesTab.notesAppearHere')
                    : t('notesTab.startMission')
                }
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
