import React, { useState, useEffect, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog'
import { Button } from '../../../components/ui/button'
import { Label } from '../../../components/ui/label'
import { Input } from '../../../components/ui/input'
import { Switch } from '../../../components/ui/switch'
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import { Settings, Save, RotateCcw, Loader2, X } from 'lucide-react'
import { useToast } from '../../../components/ui/toast'
import { apiClient } from '../../../config/api'

type MissionSettings = {
  [key: string]: number | boolean | undefined
  initial_research_max_depth?: number
  initial_research_max_questions?: number
  structured_research_rounds?: number
  writing_passes?: number
  initial_exploration_doc_results?: number
  initial_exploration_web_results?: number
  main_research_doc_results?: number
  main_research_web_results?: number
  thought_pad_context_limit?: number
  max_notes_for_assignment_reranking?: number
  max_concurrent_requests?: number
  skip_final_replanning?: boolean
}

interface MissionSettingsResponse {
  mission_id: string
  settings?: MissionSettings
  effective_settings: MissionSettings
}

interface MissionSettingsDialogProps {
  missionId?: string
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSettingsChange?: (settings: MissionSettings) => void
}

interface MissionParameterInputProps {
  field: string
  label: string
  description: string
  currentValue: number | string | undefined
  defaultValue: number
  isOverridden: boolean
  min?: number
  max?: number
  onChange: (field: string, value: number | undefined) => void
  onReset: (field: string) => void
}

const MissionParameterInput: React.FC<MissionParameterInputProps> = ({
  field,
  label,
  description,
  currentValue,
  defaultValue,
  isOverridden,
  min,
  max,
  onChange,
  onReset
}) => (
  <div className="space-y-1.5">
    <div className="flex items-center justify-between">
      <Label htmlFor={field.toString()} className="text-xs font-medium text-gray-700">
        {label}
      </Label>
      <div className="flex items-center gap-2">
        <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md font-mono">
          {defaultValue}
        </span>
        {isOverridden && (
          <Button
            variant="ghost"
            size="icon"
            className="h-4 w-4 text-gray-500 hover:text-gray-800"
            onClick={() => onReset(field)}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
    </div>
    <Input
      id={field.toString()}
      type="number"
      min={min}
      max={max}
      value={currentValue ?? ''}
      onChange={(e) => {
        const value = e.target.value === '' ? undefined : parseInt(e.target.value, 10)
        onChange(field, value)
      }}
      placeholder={`Default: ${defaultValue}`}
      className={`h-8 text-sm ${isOverridden ? 'border-blue-400 bg-blue-50 ring-1 ring-blue-200' : 'border-gray-200'}`}
    />
    <p className="text-xs text-gray-500 leading-tight">{description}</p>
  </div>
)

export const MissionSettingsDialog: React.FC<MissionSettingsDialogProps> = ({
  missionId,
  isOpen,
  onOpenChange,
  onSettingsChange
}) => {
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [missionSettings, setMissionSettings] = useState<MissionSettings>({})
  const [defaultSettings, setDefaultSettings] = useState<MissionSettings>({})
  const [originalSettings, setOriginalSettings] = useState<MissionSettings>({})
  const { addToast } = useToast()

  const loadMissionSettings = useCallback(async () => {
    if (!missionId) return
    setIsLoading(true)
    try {
      const response = await apiClient.get<MissionSettingsResponse>(`/api/missions/${missionId}/settings`)
      const { settings, effective_settings } = response.data
      setMissionSettings(settings || {})
      setOriginalSettings(settings || {})
      // The "effective" settings are the defaults if not overridden
      setDefaultSettings(effective_settings)
    } catch (error) {
      console.error('Failed to load mission settings:', error)
      addToast({ type: 'error', title: 'Settings Error', message: 'Failed to load mission settings.' })
    } finally {
      setIsLoading(false)
    }
  }, [missionId, addToast])

  useEffect(() => {
    if (isOpen) {
      loadMissionSettings()
    }
  }, [isOpen, loadMissionSettings])

  const saveSettings = async () => {
    if (!missionId) return
    setIsSaving(true)
    try {
      const response = await apiClient.post<MissionSettingsResponse>(
        `/api/missions/${missionId}/settings`,
        { settings: missionSettings }
      )
      const { settings, effective_settings } = response.data
      setMissionSettings(settings || {})
      setOriginalSettings(settings || {})
      setDefaultSettings(effective_settings)
      onSettingsChange?.(settings || {})
      addToast({ type: 'success', title: 'Settings Saved', message: 'Mission settings updated.' })
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to save mission settings:', error)
      addToast({ type: 'error', title: 'Save Error', message: 'Failed to save mission settings.' })
    } finally {
      setIsSaving(false)
    }
  }

  const resetAllChanges = () => {
    setMissionSettings(originalSettings)
  }

  const updateSetting = (key: keyof MissionSettings, value: number | boolean | undefined) => {
    setMissionSettings(prev => {
      const newSettings = { ...prev }
      if (value === undefined) {
        delete newSettings[key]
      } else {
        newSettings[key] = value
      }
      return newSettings
    })
  }
  
  const resetOneSetting = (key: keyof MissionSettings) => {
    updateSetting(key, undefined)
  }

  const hasChanges = JSON.stringify(missionSettings) !== JSON.stringify(originalSettings)

  const renderNumberInput = (
    key: string,
    label: string,
    description: string,
    min: number = 1,
    max: number = 100
  ) => (
    <MissionParameterInput
      field={key}
      label={label}
      description={description}
      currentValue={missionSettings[key] as number | undefined}
      defaultValue={defaultSettings[key] as number}
      isOverridden={missionSettings[key] !== undefined}
      min={min}
      max={max}
      onChange={updateSetting}
      onReset={resetOneSetting}
    />
  )

  const renderBooleanInput = (
    key: string,
    label: string,
    description: string
  ) => {
    const currentValue = missionSettings[key] as boolean | undefined
    const defaultValue = defaultSettings[key] as boolean
    const isOverridden = currentValue !== undefined

    return (
      <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <Label htmlFor={key.toString()} className="text-sm font-medium text-gray-700">
              {label}
            </Label>
            <div className="flex items-center gap-2">
              <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md font-mono">
                {defaultValue ? 'ON' : 'OFF'}
              </span>
              {isOverridden && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-4 w-4 text-gray-500 hover:text-gray-800"
                  onClick={() => resetOneSetting(key)}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          </div>
          <p className="text-xs text-gray-500 leading-tight">{description}</p>
        </div>
        <Switch
          id={key.toString()}
          checked={currentValue ?? defaultValue}
          onCheckedChange={(checked) => {
            // If toggling to the default value, we can remove the override
            if (checked === defaultValue) {
              resetOneSetting(key)
            } else {
              updateSetting(key, checked)
            }
          }}
          className={`ml-3 ${isOverridden ? 'data-[state=checked]:bg-blue-600' : ''}`}
        />
      </div>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle className="flex items-center space-x-2">
            <Settings className="h-5 w-5" />
            <span>Mission Settings</span>
            {missionId && (
              <span className="text-sm text-gray-500 font-normal">
                ({missionId.slice(0, 8)}...)
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            <span>Loading settings...</span>
          </div>
        ) : (
          <div className="px-6">
            <div className="space-y-6">
            <div className="text-sm text-gray-600 bg-blue-50 p-3 rounded-md">
              <p className="font-medium mb-1">Mission-Specific Settings</p>
              <p>
                These settings will override your user defaults for this mission only. 
                Leave fields empty to use your default settings. 
                Blue-highlighted fields have mission-specific overrides.
              </p>
            </div>

            {/* Compact Grid Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Research Configuration */}
              <Card className="h-fit">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    🔍 Research Configuration
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    {renderNumberInput(
                      'initial_research_max_depth',
                      'Max Depth',
                      'Initial exploration depth',
                      1,
                      10
                    )}
                    {renderNumberInput(
                      'initial_research_max_questions',
                      'Max Questions',
                      'Total questions in initial phase',
                      5,
                      100
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {renderNumberInput(
                      'structured_research_rounds',
                      'Research Rounds',
                      'Structured research cycles',
                      1,
                      10
                    )}
                    {renderNumberInput(
                      'writing_passes',
                      'Writing Passes',
                      'Initial + revision passes',
                      1,
                      10
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Search Results */}
              <Card className="h-fit">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    📄 Search Results
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    {renderNumberInput(
                      'initial_exploration_doc_results',
                      'Initial Docs',
                      'Documents for exploration',
                      1,
                      20
                    )}
                    {renderNumberInput(
                      'initial_exploration_web_results',
                      'Initial Web',
                      'Web results for exploration',
                      1,
                      10
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {renderNumberInput(
                      'main_research_doc_results',
                      'Main Docs',
                      'Documents for research',
                      1,
                      20
                    )}
                    {renderNumberInput(
                      'main_research_web_results',
                      'Main Web',
                      'Web results for research',
                      1,
                      10
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Performance & Options */}
              <Card className="lg:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    ⚡ Performance & Options
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-3">
                      {renderNumberInput(
                        'thought_pad_context_limit',
                        'Context Limit',
                        'Recent thoughts as context',
                        5,
                        50
                      )}
                    </div>
                    <div className="space-y-3">
                      {renderNumberInput(
                        'max_notes_for_assignment_reranking',
                        'Max Notes',
                        'Notes for reranking',
                        20,
                        200
                      )}
                    </div>
                    <div className="space-y-3">
                      {renderNumberInput(
                        'max_concurrent_requests',
                        'Concurrent Requests',
                        'Parallel operations',
                        1,
                        20
                      )}
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t">
                    {renderBooleanInput(
                      'skip_final_replanning',
                      'Skip Final Replanning',
                      'Skip final outline refinement for faster completion'
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            </div>
          </div>
        )}

        <div className="px-6 pb-6 pt-4 flex-shrink-0">
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              onClick={resetAllChanges}
              disabled={!hasChanges || isSaving}
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Reset Changes
            </Button>
            
            <div className="flex space-x-2">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSaving}
              >
                Cancel
              </Button>
              <Button
                onClick={saveSettings}
                disabled={!hasChanges || isSaving || !missionId}
              >
                {isSaving ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                Save Settings
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
