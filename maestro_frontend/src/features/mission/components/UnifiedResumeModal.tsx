import React, { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog'
import { Button } from '../../../components/ui/button'
import { Textarea } from '../../../components/ui/textarea'
import { AlertTriangle, FileText, CheckCircle, RotateCcw, MessageSquare } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '../../../components/ui/alert'
import { apiClient } from '../../../config/api'
import { useToast } from '../../../components/ui/toast'

interface OutlineHistory {
  round: number
  timestamp: string
  outline: any[]
  mission_goal?: string
  action?: string
}

interface UnifiedResumeModalProps {
  isOpen: boolean
  onClose: () => void
  missionId: string
  onSuccess?: () => void
}

export const UnifiedResumeModal: React.FC<UnifiedResumeModalProps> = ({
  isOpen,
  onClose,
  missionId,
  onSuccess
}) => {
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [outlineHistory, setOutlineHistory] = useState<OutlineHistory[]>([])
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { addToast } = useToast()

  // Fetch outline history when modal opens
  useEffect(() => {
    if (isOpen && missionId) {
      fetchOutlineHistory()
    }
  }, [isOpen, missionId])

  const fetchOutlineHistory = async () => {
    setIsLoadingHistory(true)
    setError(null)
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/outline-history`)
      if (response.data && response.data.outline_history) {
        setOutlineHistory(response.data.outline_history)
        // Auto-select the highest round (should be 100 for current outline, or the latest available)
        if (response.data.outline_history.length > 0) {
          const latestRound = Math.max(...response.data.outline_history.map((h: OutlineHistory) => h.round))
          setSelectedRound(latestRound)
        }
      }
    } catch (error) {
      console.error('Failed to fetch outline history:', error)
      setError('Failed to load outline history')
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to load outline history'
      })
    } finally {
      setIsLoadingHistory(false)
    }
  }

  const handleSubmit = async () => {
    if (selectedRound === null) {
      addToast({
        type: 'error',
        title: 'No Round Selected',
        message: 'Please select a round to resume from'
      })
      return
    }

    // Map special round numbers to valid values
    let actualRoundNum = selectedRound
    if (selectedRound === 999) {
      // Final outline - find the highest real round number
      const realRounds = outlineHistory.filter(h => h.round > 0 && h.round < 999)
      actualRoundNum = realRounds.length > 0 ? Math.max(...realRounds.map(h => h.round)) : 1
    }
    // For regular rounds (1, 2, etc.), use them directly

    setIsLoading(true)
    try {
      const response = await apiClient.post(`/api/missions/${missionId}/unified-resume`, {
        round_num: actualRoundNum,
        feedback: feedback.trim() || null
      })

      const message = feedback.trim() 
        ? `Outline is being revised and mission will resume from round ${selectedRound}`
        : `Mission is resuming from round ${selectedRound}`

      addToast({
        type: 'success',
        title: 'Success',
        message
      })

      if (onSuccess) {
        onSuccess()
      }
      handleClose()
    } catch (error) {
      console.error('Failed to resume mission:', error)
      addToast({
        type: 'error',
        title: 'Resume Failed',
        message: error?.response?.data?.detail || 'Failed to resume mission'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setFeedback('')
      setSelectedRound(null)
      setOutlineHistory([])
      setError(null)
      onClose()
    }
  }

  const getSelectedOutline = () => {
    if (selectedRound === null) return null
    return outlineHistory.find(h => h.round === selectedRound)
  }

  const selectedOutline = getSelectedOutline()

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-hidden flex flex-col p-6">
        <DialogHeader className="pb-4">
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5" />
            Resume Research Mission
          </DialogTitle>
          <DialogDescription className="mt-2">
            Select a research round to resume from and optionally provide feedback to revise the outline.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert className="border-red-500/50 bg-red-500/10 mb-4">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex-1 overflow-hidden grid grid-cols-2 gap-6 min-h-0">
          {/* Left side - Round selection */}
          <div className="flex flex-col min-h-0">
            <h3 className="text-sm font-semibold mb-3">Available Research Rounds</h3>
            {isLoadingHistory ? (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Loading outline history...</p>
              </div>
            ) : outlineHistory.length === 0 ? (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-muted-foreground">No research rounds available</p>
              </div>
            ) : (
              <div className="flex-1 border rounded-lg p-2 overflow-y-auto min-h-0">
                <div className="space-y-2">
                  {outlineHistory.map((history) => (
                    <button
                      key={history.round}
                      onClick={() => setSelectedRound(history.round)}
                      className={`w-full text-left p-3 rounded-lg border transition-colors ${
                        selectedRound === history.round
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:bg-secondary/50'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <CheckCircle className={`h-4 w-4 ${
                              selectedRound === history.round ? 'text-primary' : 'text-muted-foreground'
                            }`} />
                            <span className="font-medium text-sm">
                              {history.action || (history.round === 999 ? 'Final Outline' : `Round ${history.round} Outline`)}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {new Date(history.timestamp).toLocaleString()}
                          </p>
                          {history.outline && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {history.outline.length} sections
                            </p>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right side - Selected outline preview */}
          <div className="flex flex-col min-h-0">
            <h3 className="text-sm font-semibold mb-3">
              {selectedOutline ? (
                selectedOutline.action || (selectedOutline.round === 999 ? 'Final Outline' : `Round ${selectedOutline.round} Outline`)
              ) : 'Select a Round'}
            </h3>
            {selectedOutline ? (
              <div className="flex-1 border rounded-lg p-3 overflow-y-auto min-h-0">
                <div className="space-y-3">
                  {selectedOutline.mission_goal && (
                    <div className="pb-3 border-b">
                      <h4 className="text-xs font-medium text-muted-foreground mb-1">Mission Goal</h4>
                      <p className="text-sm">{selectedOutline.mission_goal}</p>
                    </div>
                  )}
                  {selectedOutline.outline && selectedOutline.outline.map((section: any, index: number) => (
                    <div key={index} className="space-y-1">
                      <div className="flex items-start gap-2">
                        <FileText className="h-3 w-3 text-muted-foreground mt-0.5" />
                        <div className="flex-1">
                          <p className="text-sm font-medium">
                            {index + 1}. {section.title || section.section_id}
                          </p>
                          {section.description && (
                            <p className="text-xs text-muted-foreground mt-1">{section.description}</p>
                          )}
                          {section.subsections && section.subsections.length > 0 && (
                            <div className="ml-4 mt-2 space-y-1">
                              {section.subsections.map((sub: any, subIndex: number) => (
                                <p key={subIndex} className="text-xs text-muted-foreground">
                                  {index + 1}.{subIndex + 1} {sub.title || sub.section_id}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex-1 border rounded-lg flex items-center justify-center">
                <p className="text-sm text-muted-foreground">
                  Select a round to preview its outline
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Feedback section */}
        <div className="space-y-3 border-t pt-4 mt-4">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            <label htmlFor="feedback" className="text-sm font-medium">
              Optional Feedback for Outline Revision
            </label>
          </div>
          <Textarea
            id="feedback"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Leave empty to resume without changes, or provide feedback to revise the outline. For example:
- Add a section about X
- Remove the section on Y
- Focus more on Z aspect
- Reorganize sections to flow better"
            className="min-h-[80px] resize-none text-sm"
            disabled={isLoading || selectedRound === null}
          />
          <p className="text-xs text-muted-foreground">
            {feedback.trim() 
              ? 'The outline will be revised based on your feedback before resuming.'
              : 'The mission will resume from the selected round without changes.'}
          </p>
        </div>

        <DialogFooter className="gap-2 pt-4 border-t">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isLoading || selectedRound === null || isLoadingHistory}
          >
            {isLoading ? 'Processing...' : (feedback.trim() ? 'Revise & Resume' : 'Resume')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}