import React, { useState, useEffect } from 'react'
import { Button } from '../../../components/ui/button'
import { useToast } from '../../../components/ui/toast'
import { X, Save, RotateCcw } from 'lucide-react'
import { apiClient } from '../../../config/api'

interface CustomSystemPromptModalProps {
  isOpen: boolean
  onClose: () => void
}

const DEFAULT_ADDITIONAL_INSTRUCTIONS = `Use bullet points only sparingly and only if absolutely necessary. Otherwise, write in reasonably length paragraphs that flow naturally and provide comprehensive coverage of topics.`

export const CustomSystemPromptModal: React.FC<CustomSystemPromptModalProps> = ({
  isOpen,
  onClose
}) => {
  const [additionalInstructions, setAdditionalInstructions] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [originalInstructions, setOriginalInstructions] = useState('')
  const { addToast } = useToast()

  // Load current custom system prompt when modal opens
  useEffect(() => {
    if (isOpen) {
      loadCurrentSettings()
    }
  }, [isOpen])

  // Track changes
  useEffect(() => {
    setHasChanges(additionalInstructions !== originalInstructions)
  }, [additionalInstructions, originalInstructions])

  const loadCurrentSettings = async () => {
    try {
      const response = await apiClient.get('/api/me/settings')
      const settings = response.data
      const writingSettings = settings.writing_settings || {}
      const currentInstructions = writingSettings.custom_system_prompt || ''
      
      setAdditionalInstructions(currentInstructions)
      setOriginalInstructions(currentInstructions)
      setHasChanges(false)
    } catch (error) {
      console.error('Failed to load user settings:', error)
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to load current settings.',
        duration: 5000
      })
    }
  }

  const handleSave = async () => {
    setIsLoading(true)
    try {
      // Get current settings first
      const currentSettingsResponse = await apiClient.get('/api/me/settings')
      const currentSettings = currentSettingsResponse.data

      // Update writing settings with custom system prompt
      const updatedSettings = {
        ...currentSettings,
        writing_settings: {
          ...currentSettings.writing_settings,
          custom_system_prompt: additionalInstructions.trim()
        }
      }

      await apiClient.put('/api/me/settings', { settings: updatedSettings })

      addToast({
        type: 'success',
        title: 'Settings Saved',
        message: 'Additional instructions have been updated successfully.',
        duration: 3000
      })

      setOriginalInstructions(additionalInstructions.trim())
      setHasChanges(false)
      onClose()
    } catch (error) {
      console.error('Failed to save custom system prompt:', error)
      addToast({
        type: 'error',
        title: 'Save Failed',
        message: 'Failed to save custom system prompt. Please try again.',
        duration: 5000
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = () => {
    if (window.confirm('Are you sure you want to reset to the default additional instructions? This will overwrite your current custom instructions.')) {
      setAdditionalInstructions(DEFAULT_ADDITIONAL_INSTRUCTIONS)
    }
  }

  const handleClear = () => {
    if (window.confirm('Are you sure you want to clear the additional instructions? The agent will use only the default prompt.')) {
      setAdditionalInstructions('')
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background border border-border rounded-lg shadow-lg w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Additional Instructions
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Add custom instructions that will be appended to the default system prompt
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Additional Instructions
              </label>
              <textarea
                value={additionalInstructions}
                onChange={(e) => setAdditionalInstructions(e.target.value)}
                placeholder="Enter additional instructions to be added to the default system prompt..."
                className="w-full h-80 p-3 border border-border rounded-md bg-background text-foreground text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                disabled={isLoading}
              />
              <p className="text-xs text-muted-foreground mt-2">
                {additionalInstructions.length} characters
                {additionalInstructions.trim() === '' && ' (will use default prompt only)'}
              </p>
            </div>

            <div className="bg-muted/50 border border-border rounded-md p-4">
              <h4 className="text-sm font-medium text-foreground mb-2">
                How it Works
              </h4>
              <p className="text-xs text-muted-foreground">
                Your additional instructions will be appended to the default system prompt. The agent will 
                follow both the default behavior and your custom instructions when generating responses.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-border">
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              disabled={isLoading}
              className="text-xs"
            >
              <RotateCcw className="h-3 w-3 mr-1" />
              Reset to Default
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleClear}
              disabled={isLoading}
              className="text-xs"
            >
              Clear
            </Button>
          </div>
          
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={isLoading || !hasChanges}
              className="min-w-[80px]"
            >
              {isLoading ? (
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Saving...
                </div>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
