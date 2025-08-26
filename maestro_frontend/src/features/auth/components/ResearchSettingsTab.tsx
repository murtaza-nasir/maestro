import React, { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { type ResearchParameters, useSettingsStore } from './SettingsStore'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Switch } from '../../../components/ui/switch'
import { Info, RotateCcw, X, BarChart3, Search, Zap, Bot, FileText, Layers, ListChecks, FileCode, Settings2 } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select'

// Default values for research parameters
const DEFAULT_RESEARCH_PARAMS: ResearchParameters = {
  initial_research_max_depth: 3,
  initial_research_max_questions: 15,
  structured_research_rounds: 2,
  writing_passes: 2,
  initial_exploration_doc_results: 5,
  initial_exploration_web_results: 3,
  main_research_doc_results: 5,
  main_research_web_results: 5,
  thought_pad_context_limit: 5,
  max_notes_for_assignment_reranking: 80,
  max_concurrent_requests: 10,
  skip_final_replanning: false,
  auto_optimize_params: false,
  max_research_cycles_per_section: 2,
  max_total_iterations: 40,
  max_total_depth: 2,
  min_notes_per_section_assignment: 5,
  max_notes_per_section_assignment: 40,
  max_planning_context_chars: 250000,
  writing_previous_content_preview_chars: 30000,
  research_note_content_limit: 32000,
  writing_search_max_iterations: 1,
  writing_search_max_queries: 3,
  writing_deep_search_iterations: 3,
  writing_deep_search_queries: 5
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
  const { t } = useTranslation()
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const RESEARCH_PRESETS = {
    'quick': {
      name: t('researchSettings.quickAndSimple'),
      description: t('researchSettings.quickAndSimpleDescription'),
      params: { ...DEFAULT_RESEARCH_PARAMS, initial_research_max_depth: 1, initial_research_max_questions: 5, structured_research_rounds: 1, writing_passes: 1, initial_exploration_doc_results: 3, initial_exploration_web_results: 2, main_research_doc_results: 3, main_research_web_results: 0, thought_pad_context_limit: 3, max_notes_for_assignment_reranking: 30, max_concurrent_requests: 5, skip_final_replanning: true, max_research_cycles_per_section: 1, max_total_iterations: 20, max_total_depth: 1, min_notes_per_section_assignment: 3, max_notes_per_section_assignment: 20, max_planning_context_chars: 150000, writing_previous_content_preview_chars: 20000, research_note_content_limit: 20000 }
    },
    'balanced': {
      name: t('researchSettings.balancedResearch'),
      description: t('researchSettings.balancedResearchDescription'),
      params: DEFAULT_RESEARCH_PARAMS
    },
    'deep': {
      name: t('researchSettings.deepAnalysis'),
      description: t('researchSettings.deepAnalysisDescription'),
      params: { ...DEFAULT_RESEARCH_PARAMS, initial_research_max_depth: 5, initial_research_max_questions: 30, structured_research_rounds: 4, writing_passes: 4, initial_exploration_doc_results: 8, initial_exploration_web_results: 5, main_research_doc_results: 10, main_research_web_results: 5, thought_pad_context_limit: 10, max_notes_for_assignment_reranking: 150, max_concurrent_requests: 20, max_research_cycles_per_section: 4, max_total_iterations: 80, max_total_depth: 4, min_notes_per_section_assignment: 10, max_notes_per_section_assignment: 80, max_planning_context_chars: 400000, writing_previous_content_preview_chars: 40000, research_note_content_limit: 40000 }
    },
    'academic': {
      name: t('researchSettings.academicPaper'),
      description: t('researchSettings.academicPaperDescription'),
      params: { ...DEFAULT_RESEARCH_PARAMS, initial_research_max_depth: 4, initial_research_max_questions: 25, structured_research_rounds: 3, writing_passes: 3, initial_exploration_doc_results: 10, initial_exploration_web_results: 2, main_research_doc_results: 15, main_research_web_results: 0, thought_pad_context_limit: 8, max_notes_for_assignment_reranking: 120, max_concurrent_requests: 15, max_research_cycles_per_section: 3, max_total_iterations: 60, max_total_depth: 3, min_notes_per_section_assignment: 8, max_notes_per_section_assignment: 60, max_planning_context_chars: 350000, writing_previous_content_preview_chars: 35000, research_note_content_limit: 35000 }
    },
    'current_events': {
      name: t('researchSettings.currentEvents'),
      description: t('researchSettings.currentEventsDescription'),
      params: { ...DEFAULT_RESEARCH_PARAMS, initial_research_max_depth: 2, initial_research_max_questions: 12, structured_research_rounds: 2, writing_passes: 2, initial_exploration_doc_results: 2, initial_exploration_web_results: 8, main_research_doc_results: 2, main_research_web_results: 10, thought_pad_context_limit: 5, max_notes_for_assignment_reranking: 60, max_concurrent_requests: 10, skip_final_replanning: true, max_research_cycles_per_section: 2, max_total_iterations: 30, max_total_depth: 2, min_notes_per_section_assignment: 4, max_notes_per_section_assignment: 30, max_planning_context_chars: 200000, writing_previous_content_preview_chars: 25000, research_note_content_limit: 25000 }
    }
  }

  const resetToDefaults = useCallback(() => {
    setDraftSettings({ research_parameters: { ...DEFAULT_RESEARCH_PARAMS } })
  }, [setDraftSettings])

  const applyPreset = useCallback((presetKey: string) => {
    if (presetKey === 'custom') {
      return
    }
    const preset = RESEARCH_PRESETS[presetKey as keyof typeof RESEARCH_PRESETS]
    if (preset) {
      setDraftSettings({ research_parameters: { ...preset.params } })
    }
  }, [setDraftSettings, RESEARCH_PRESETS])

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
    return <div>{t('researchSettings.loading')}</div>
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
                {t('researchSettings.title')}
              </CardTitle>
              <CardDescription className="text-sm">
                {t('researchSettings.description')}
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
              {t('researchSettings.resetToDefaults')}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Card className="p-3 bg-gradient-to-r from-blue-50 via-cyan-50 to-teal-50 dark:from-blue-900/20 dark:via-cyan-900/20 dark:to-teal-900/20 border-blue-200 dark:border-blue-700">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Settings2 className="h-4 w-4" />
                  {t('researchSettings.quickPresets')}
                </h3>
                <p className="text-xs text-muted-foreground-foreground">{t('researchSettings.quickPresetsDescription')}</p>
              </div>
              <Select onValueChange={applyPreset}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder={t('researchSettings.selectPreset')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="quick">
                    <div>
                      <div className="font-medium">{t('researchSettings.quickAndSimple')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.quickAndSimpleDescription')}</div>
                    </div>
                  </SelectItem>
                  <SelectItem value="balanced">
                    <div>
                      <div className="font-medium">{t('researchSettings.balancedResearch')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.balancedResearchDescription')}</div>
                    </div>
                  </SelectItem>
                  <SelectItem value="deep">
                    <div>
                      <div className="font-medium">{t('researchSettings.deepAnalysis')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.deepAnalysisDescription')}</div>
                    </div>
                  </SelectItem>
                  <SelectItem value="academic">
                    <div>
                      <div className="font-medium">{t('researchSettings.academicPaper')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.academicPaperDescription')}</div>
                    </div>
                  </SelectItem>
                  <SelectItem value="current_events">
                    <div>
                      <div className="font-medium">{t('researchSettings.currentEvents')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.currentEventsDescription')}</div>
                    </div>
                  </SelectItem>
                  <SelectItem value="custom">
                    <div>
                      <div className="font-medium">{t('researchSettings.custom')}</div>
                      <div className="text-xs text-muted-foreground">{t('researchSettings.customDescription')}</div>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </Card>

          <Card className="p-3 bg-gradient-to-r from-purple-50 via-fuchsia-50 to-rose-50 dark:from-purple-900/20 dark:via-fuchsia-900/20 dark:to-rose-900/20 border-purple-200 dark:border-purple-700">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Bot className="h-4 w-4" />
                  {t('researchSettings.aiPoweredConfiguration')}
                </h3>
                <p className="text-xs text-muted-foreground-foreground">{t('researchSettings.aiPoweredConfigurationDescription')}</p>
              </div>
              <Switch
                checked={isAutoOptimizeEnabled}
                onCheckedChange={(checked) => handleBooleanChange('auto_optimize_params', checked)}
              />
            </div>
          </Card>

          <div className={`grid grid-cols-1 lg:grid-cols-2 gap-4 ${isAutoOptimizeEnabled ? 'opacity-50 pointer-events-none' : ''}`}>
            <Card className="p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Search className="h-4 w-4" />
                {t('researchSettings.researchConfiguration')}
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <ResearchParameterInput
                  field="initial_research_max_depth"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.maxDepth')}
                  description={t('researchSettings.maxDepthDescription')}
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
                  label={t('researchSettings.maxQuestions')}
                  description={t('researchSettings.maxQuestionsDescription')}
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
                  label={t('researchSettings.researchRounds')}
                  description={t('researchSettings.researchRoundsDescription')}
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
                  label={t('researchSettings.writingPasses')}
                  description={t('researchSettings.writingPassesDescription')}
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

            <Card className="p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <FileText className="h-4 w-4" />
                {t('researchSettings.searchResults')}
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <ResearchParameterInput
                  field="initial_exploration_doc_results"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.initialDocs')}
                  description={t('researchSettings.initialDocsDescription')}
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
                  label={t('researchSettings.initialWeb')}
                  description={t('researchSettings.initialWebDescription')}
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
                  label={t('researchSettings.mainDocs')}
                  description={t('researchSettings.mainDocsDescription')}
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
                  label={t('researchSettings.mainWeb')}
                  description={t('researchSettings.mainWebDescription')}
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

            <Card className="lg:col-span-2 p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Zap className="h-4 w-4" />
                {t('researchSettings.performanceAndOptions')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ResearchParameterInput
                  field="thought_pad_context_limit"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.contextLimit')}
                  description={t('researchSettings.contextLimitDescription')}
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
                  label={t('researchSettings.maxNotes')}
                  description={t('researchSettings.maxNotesDescription')}
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
                  label={t('researchSettings.concurrentRequests')}
                  description={t('researchSettings.concurrentRequestsDescription')}
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
                      {t('researchSettings.skipFinalReplanning')}
                      <Info className="h-3 w-3 text-muted-foreground" />
                    </Label>
                    <p className="text-xs text-muted-foreground">{t('researchSettings.skipFinalReplanningDescription')}</p>
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

            <Card className="lg:col-span-2 p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Layers className="h-4 w-4" />
                {t('researchSettings.advancedResearchLoopConfiguration')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ResearchParameterInput
                  field="max_research_cycles_per_section"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.researchCyclesPerSection')}
                  description={t('researchSettings.researchCyclesPerSectionDescription')}
                  value={params.max_research_cycles_per_section ?? DEFAULT_RESEARCH_PARAMS.max_research_cycles_per_section!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_research_cycles_per_section as number}
                  min={1}
                  max={5}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="max_total_iterations"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.totalIterations')}
                  description={t('researchSettings.totalIterationsDescription')}
                  value={params.max_total_iterations ?? DEFAULT_RESEARCH_PARAMS.max_total_iterations!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_total_iterations as number}
                  min={10}
                  max={100}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="max_total_depth"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.maxOutlineDepth')}
                  description={t('researchSettings.maxOutlineDepthDescription')}
                  value={params.max_total_depth ?? DEFAULT_RESEARCH_PARAMS.max_total_depth!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_total_depth as number}
                  min={1}
                  max={5}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>

            <Card className="lg:col-span-2 p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <ListChecks className="h-4 w-4" />
                {t('researchSettings.noteAssignmentLimits')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <ResearchParameterInput
                  field="min_notes_per_section_assignment"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.minNotesPerSection')}
                  description={t('researchSettings.minNotesPerSectionDescription')}
                  value={params.min_notes_per_section_assignment ?? DEFAULT_RESEARCH_PARAMS.min_notes_per_section_assignment!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.min_notes_per_section_assignment as number}
                  min={1}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="max_notes_per_section_assignment"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.maxNotesPerSection')}
                  description={t('researchSettings.maxNotesPerSectionDescription')}
                  value={params.max_notes_per_section_assignment ?? DEFAULT_RESEARCH_PARAMS.max_notes_per_section_assignment!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_notes_per_section_assignment as number}
                  min={10}
                  max={100}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>

            <Card className="lg:col-span-2 p-3">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <FileCode className="h-4 w-4" />
                {t('researchSettings.contentProcessingLimits')}
                <span className="text-xs badge-default px-1.5 py-0.5 rounded-md">{t('researchSettings.advanced')}</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ResearchParameterInput
                  field="max_planning_context_chars"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.planningContext')}
                  description={t('researchSettings.planningContextDescription')}
                  value={params.max_planning_context_chars ?? DEFAULT_RESEARCH_PARAMS.max_planning_context_chars!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.max_planning_context_chars as number}
                  min={50000}
                  max={500000}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="writing_previous_content_preview_chars"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.writingPreview')}
                  description={t('researchSettings.writingPreviewDescription')}
                  value={params.writing_previous_content_preview_chars ?? DEFAULT_RESEARCH_PARAMS.writing_previous_content_preview_chars!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_previous_content_preview_chars as number}
                  min={10000}
                  max={50000}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="research_note_content_limit"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.noteContentLimit')}
                  description={t('researchSettings.noteContentLimitDescription')}
                  value={params.research_note_content_limit ?? DEFAULT_RESEARCH_PARAMS.research_note_content_limit!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.research_note_content_limit as number}
                  min={10000}
                  max={50000}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>
            
            <Card className="border-muted/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium">{t('researchSettings.writingModeSearchSettings')}</CardTitle>
                <CardDescription className="text-xs">{t('researchSettings.writingModeSearchSettingsDescription')}</CardDescription>
              </CardHeader>
              <div className="px-6 pb-4 grid grid-cols-2 gap-3">
                <ResearchParameterInput
                  field="writing_search_max_iterations"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.regularSearchIterations')}
                  description={t('researchSettings.regularSearchIterationsDescription')}
                  value={params.writing_search_max_iterations ?? DEFAULT_RESEARCH_PARAMS.writing_search_max_iterations!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_search_max_iterations as number}
                  min={1}
                  max={5}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="writing_search_max_queries"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.regularSearchQueries')}
                  description={t('researchSettings.regularSearchQueriesDescription')}
                  value={params.writing_search_max_queries ?? DEFAULT_RESEARCH_PARAMS.writing_search_max_queries!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_search_max_queries as number}
                  min={1}
                  max={10}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="writing_deep_search_iterations"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.deepSearchIterations')}
                  description={t('researchSettings.deepSearchIterationsDescription')}
                  value={params.writing_deep_search_iterations ?? DEFAULT_RESEARCH_PARAMS.writing_deep_search_iterations!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_deep_search_iterations as number}
                  min={1}
                  max={10}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
                <ResearchParameterInput
                  field="writing_deep_search_queries"
                  disabled={isAutoOptimizeEnabled}
                  label={t('researchSettings.deepSearchQueries')}
                  description={t('researchSettings.deepSearchQueriesDescription')}
                  value={params.writing_deep_search_queries ?? DEFAULT_RESEARCH_PARAMS.writing_deep_search_queries!}
                  defaultValue={DEFAULT_RESEARCH_PARAMS.writing_deep_search_queries as number}
                  min={1}
                  max={20}
                  onChange={handleNumberChange}
                  onBlur={handleBlur}
                  onReset={handleResetParameter}
                />
              </div>
            </Card>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
