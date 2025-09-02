import React, { useState } from 'react'
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
import { AlertTriangle, MessageSquare } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '../../../components/ui/alert'

interface OutlineRevisionModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (feedback: string) => void
  isLoading?: boolean
  currentOutline?: any
}

export const OutlineRevisionModal: React.FC<OutlineRevisionModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
  currentOutline
}) => {
  const [feedback, setFeedback] = useState('')

  const handleSubmit = () => {
    if (feedback.trim()) {
      onSubmit(feedback)
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setFeedback('')
      onClose()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Revise Research Outline
          </DialogTitle>
          <DialogDescription>
            Provide feedback to improve the research outline. The mission will be restarted with the revised outline.
          </DialogDescription>
        </DialogHeader>

        <Alert className="border-yellow-500/50 bg-yellow-500/10">
          <AlertTriangle className="h-4 w-4 text-yellow-500" />
          <AlertTitle>Important</AlertTitle>
          <AlertDescription>
            Revising the outline will halt the current mission execution and restart it with the updated plan.
            Any progress from the current execution will be preserved in the mission history.
          </AlertDescription>
        </Alert>

        <div className="flex-1 overflow-hidden flex flex-col space-y-4">
          {currentOutline && (
            <div className="border rounded-lg p-3 bg-secondary/50 max-h-48 overflow-y-auto">
              <h4 className="text-sm font-medium mb-2">Current Outline</h4>
              <div className="space-y-1 text-xs text-muted-foreground">
                {Array.isArray(currentOutline) ? (
                  currentOutline.map((section: any, index: number) => (
                    <div key={index}>
                      {index + 1}. {section.title || section.section_id}
                      {section.subsections && section.subsections.length > 0 && (
                        <span className="ml-2 text-muted-foreground">
                          ({section.subsections.length} subsections)
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <pre className="whitespace-pre-wrap">
                    {JSON.stringify(currentOutline, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          )}

          <div className="flex-1 flex flex-col">
            <label htmlFor="feedback" className="text-sm font-medium mb-2">
              Your Feedback
            </label>
            <Textarea
              id="feedback"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Describe what changes you'd like to see in the outline. For example:
- Add a section about X
- Remove the section on Y
- Focus more on Z aspect
- Reorganize sections to flow better"
              className="flex-1 min-h-[150px] resize-none"
              disabled={isLoading}
            />
            <p className="text-xs text-muted-foreground mt-2">
              Be specific about what sections to add, remove, or modify.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isLoading || !feedback.trim()}
          >
            {isLoading ? 'Revising...' : 'Revise Outline'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}