import React, { useCallback } from 'react'
import { type ResearchParameters, useSettingsStore } from './SettingsStore'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Switch } from '../../../components/ui/switch'
import { Info, RotateCcw, X, BarChart3, Search, Zap, Bot, FileText } from 'lucide-react'

// Default values for research parameters
const DEFAULT_RESEARCH_PARAMS: ResearchParameters = {
  initial_research_max_depth: 3,
  initial_research_max_questions: 15,
  structured_research_rounds: 3,
  writing_passes: 4,
  initial_exploration_doc_results: 5,
  initial_exploration_web_results: 3,
  main_research_doc_results: 5,
  main_research_web_results: 0,
  thought_pad_context_limit: 5,
  max_notes_for_assignment_reranking: 0,
  max_concurrent_requests: 80,
  skip_final_replanning: false,
  auto_optimize_params: false
}

interface ResearchParameterInputProps {
  field: keyof ResearchParameters
  label: string
  description: string
  value: number | string
  defaultValue: number
  min?: number
  max?: number
  onChange: (field: keyof ResearchParameters, value: string) => void
  onBlur: (field: keyof ResearchParameters, value: string) => void
  onReset: (field: keyof ResearchParameters) => void
  disabled?: boolean
}

const ResearchParameterInput: React.FC<ResearchParameterInputProps> = ({
  field,
  label,
  description,
  value,
  defaultValue,
  min,
  max,
  onChange,
  onBlur,
  onReset,
  disabled = false
}) => {
  const isModified = value !== defaultValue

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <Label htmlFor={field} className="text-xs">
          {label}
        </Label>
        <div className="flex items-center gap-2">
          <span className="text-xs badge-default px-1.5 py-0.5 rounded-md font-mono">
            {defaultValue}
          </span>
          {isModified && (
            <Button
              variant="ghost"
              size="icon"
              className="h-4 w-4 text-interactive"
              onClick={() => onReset(field)}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
      <Input
        id={field}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(field, e.target.value)}
        onBlur={(e) => onBlur(field, e.target.value)}
        className={`h-8 text-sm ${isModified ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20 ring-1 ring-blue-200 dark:ring-blue-700' : 'border-gray-200 dark:border-gray-600'}`}
        disabled={disabled}
      />
      <p className="text-xs text-muted-foreground-foreground">{description}</p>
    </div>
  )
}

export const ResearchSettingsTab: React.FC = () => {
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const resetToDefaults = useCallback(() => {
    setDraftSettings({ research_parameters: { ...DEFAULT_RESEARCH_PARAMS } })
  }, [setDraftSettings])

  const handleNumberChange = useCallback((field: keyof ResearchParameters, value: string) => {
    const numValue = parseInt(value, 10)
    setDraftSettings({
      research_parameters: {
        ...draftSettings!.research_parameters,
        [field]: isNaN(numValue) ? '' : numValue
      }
    })
  }, [draftSettings, setDraftSettings])

  const handleBlur = useCallback((field: keyof ResearchParameters, value: string) => {
    if (value === '') {
      setDraftSettings({
        research_parameters: {
          ...draftSettings!.research_parameters,
          [field]: DEFAULT_RESEARCH_PARAMS[field]
        }
      })
    }
  }, [draftSettings, setDraftSettings])

  const handleBooleanChange = useCallback((field: keyof ResearchParameters, value: boolean) => {
    setDraftSettings({
      research_parameters: {
        ...draftSettings!.research_parameters,
        [field]: value
      }
    })
  }, [draftSettings, setDraftSettings])

  const handleResetParameter = useCallback((field: keyof ResearchParameters) => {
    setDraftSettings({
      research_parameters: {
        ...draftSettings!.research_parameters,
        [field]: DEFAULT_RESEARCH_PARAMS[field]
      }
    })
  }, [draftSettings, setDraftSettings])

  if (!draftSettings) {
    return <div>Loading...</div>
  }

  const params = draftSettings.research_parameters
  const isAutoOptimizeEnabled = params.auto_optimize_params

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Research Parameters
              </CardTitle>
              <CardDescription className="text-sm">
                Configure default values for research parameters. These can be overridden per mission.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={resetToDefaults}
              className="flex items-center gap-2"
              disabled={isAutoOptimizeEnabled}
            >
              <RotateCcw className="h-3 w-3" />
              Reset to Defaults
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* AI-Powered Configuration */}
          <Card className="p-3 bg-gradient-to-r from-purple-50 via-fuchsia-50 to-rose-50 dark:from-purple-900/20 dark:via-fuchsia-900/20 dark:to-rose-900/20 border-purple-200 dark:border-purple-700">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Bot className="h-4 w-4" />
                  AI-Powered Configuration
                </h3>
                <p className="text-xs text-muted-foreground-foreground">Let an AI agent dynamically optimize parameters based on your request.</p>
              </div>
              <Switch
                checked={isAutoOptimizeEnabled}
                onCheckedChange={(checked) => handleBooleanChange('auto_optimize_params', checked)}
              />
            </div>
          </Card>

          <div className={`grid grid-cols-1 lg:grid-cols-2 gap-4 ${isAutoOptimizeEnabled ? 'opacity-50 pointer-events-none' : ''}`}>
            {/* Research Configuration */}
            <Card className="p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Search className="h-4 w-4" />
                Research Configuration
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <ResearchParameterInput
                  field="initial_research_max_depth"
                  disabled={isAutoOptimizeEnabled}
                  label="Max Depth"
                  description="Initial exploration depth"
                  value={params.initial_research_max_depth}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.initial_research_max_depth as number}
                  min={1}
                  max={10}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="initial_research_max_questions"
                  disabled={isAutoOptimizeEnabled}
                  label="Max Questions"
                  description="Questions for initial research"
                  value={params.initial_research_max_questions}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.initial_research_max_questions as number}
                  min={1}
                  max={50}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="structured_research_rounds"
                  disabled={isAutoOptimizeEnabled}
                  label="Research Rounds"
                  description="Structured research cycles"
                  value={params.structured_research_rounds}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.structured_research_rounds as number}
                  min={1}
                  max={10}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="writing_passes"
                  disabled={isAutoOptimizeEnabled}
                  label="Writing Passes"
                  description="Report writing passes"
                  value={params.writing_passes}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_passes as number}
                  min={1}
                  max={10}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>

            {/* Search Results */}
            <Card className="p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Search Results
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <ResearchParameterInput
                  field="initial_exploration_doc_results"
                  disabled={isAutoOptimizeEnabled}
                  label="Initial Docs"
                  description="Documents for exploration"
                  value={params.initial_exploration_doc_results}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.initial_exploration_doc_results as number}
                  min={1}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="initial_exploration_web_results"
                  disabled={isAutoOptimizeEnabled}
                  label="Initial Web"
                  description="Web results for exploration"
                  value={params.initial_exploration_web_results}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.initial_exploration_web_results as number}
                  min={1}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="main_research_doc_results"
                  disabled={isAutoOptimizeEnabled}
                  label="Main Docs"
                  description="Documents for research"
                  value={params.main_research_doc_results}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.main_research_doc_results as number}
                  min={1}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="main_research_web_results"
                  disabled={isAutoOptimizeEnabled}
                  label="Main Web"
                  description="Web results for research"
                  value={params.main_research_web_results}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.main_research_web_results as number}
                  min={0}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>

            {/* Performance & Options */}
            <Card className="lg:col-span-2 p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Zap className="h-4 w-4" />
                Performance & Options
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ResearchParameterInput
                  field="thought_pad_context_limit"
                  disabled={isAutoOptimizeEnabled}
                  label="Context Limit"
                  description="Thoughts in context"
                  value={params.thought_pad_context_limit}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.thought_pad_context_limit as number}
                  min={1}
                  max={50}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="max_notes_for_assignment_reranking"
                  disabled={isAutoOptimizeEnabled}
                  label="Max Notes"
                  description="Notes for reranking"
                  value={params.max_notes_for_assignment_reranking}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_notes_for_assignment_reranking as number}
                  min={0}
                  max={200}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="max_concurrent_requests"
                  disabled={isAutoOptimizeEnabled}
                  label="Concurrent Requests"
                  description="Parallel operations"
                  value={params.max_concurrent_requests}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_concurrent_requests as number}
                  min={1}
                  max={100}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
              <div className="mt-4 pt-3 border-t">
                <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
                  <div className="flex-1">
                    <Label htmlFor="skip-final-replanning" className="text-sm font-medium flex items-center gap-2">
                      Skip Final Replanning
                      <Info className="h-3 w-3 text-muted-foreground" />
                    </Label>
                    <p className="text-xs text-muted-foreground">Skip final replanning for faster completion</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs badge-default px-1.5 py-0.5 rounded-md font-mono">
                      {DEFAULT_RESEARCH_PARAMS.skip_final_replanning ? 'ON' : 'OFF'}
                    </span>
                    {params.skip_final_replanning !== DEFAULT_RESEARCH_PARAMS.skip_final_replanning && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4 text-interactive"
                        onClick={() => handleResetParameter('skip_final_replanning')}
                        disabled={isAutoOptimizeEnabled}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    )}
                    <Switch
                      id="skip-final-replanning"
                      checked={params.skip_final_replanning}
                      onCheckedChange={(checked) => handleBooleanChange('skip_final_replanning', checked)}
                      className={`${params.skip_final_replanning !== DEFAULT_RESEARCH_PARAMS.skip_final_replanning ? 'data-[state=checked]:bg-blue-600' : ''}`}
                      disabled={isAutoOptimizeEnabled}
                    />
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
