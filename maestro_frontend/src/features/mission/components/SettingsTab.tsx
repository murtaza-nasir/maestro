import React, { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import { Badge } from '../../../components/ui/badge'
import { useMissionStore } from '../store'
import { useChatStore } from '../../chat/store'
import { apiClient } from '../../../config/api'
import { Loader2, Settings, Globe, FileText, Brain, DollarSign, Hash, Save, Layers, Search, Database, Clock } from 'lucide-react'

interface SettingsTabProps {
  missionId: string
}

interface ComprehensiveMissionSettings {
  mission_id?: string
  status?: string
  created_at?: string
  user_request?: string
  comprehensive_settings?: {
    use_web_search?: boolean
    use_local_rag?: boolean
    document_group_id?: string
    document_group_name?: string
    model_config?: {
      fast_provider?: string
      fast_model?: string
      mid_provider?: string
      mid_model?: string
      intelligent_provider?: string
      intelligent_model?: string
      verifier_provider?: string
      verifier_model?: string
    }
    research_params?: any
    search_provider?: string
    web_fetch_settings?: any
    all_user_settings?: any
    settings_captured_at?: string
    settings_captured_at_start?: boolean
    start_time_capture?: string
    start_method?: string
    settings_not_captured?: boolean
    message?: string
  }
  mission_specific_settings?: any
  tool_selection?: {
    web_search?: boolean
    local_rag?: boolean
  }
  document_group_id?: string
  total_cost?: number
  total_tokens?: {
    prompt?: number
    completion?: number
    native?: number
  }
  total_web_searches?: number
}

export const SettingsTab: React.FC<SettingsTabProps> = ({ missionId }) => {
  const [settings, setSettings] = useState<ComprehensiveMissionSettings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const { missions } = useMissionStore()
  const { activeChat } = useChatStore()
  
  const mission = missions.find(m => m.id === missionId)

  useEffect(() => {
    const fetchSettings = async () => {
      if (!missionId) return
      
      setIsLoading(true)
      try {
        // Fetch comprehensive mission settings
        const response = await apiClient.get(`/api/missions/${missionId}/comprehensive-settings`)
        setSettings(response.data)
      } catch (error) {
        console.error('Failed to fetch mission settings:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchSettings()
  }, [missionId])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">No settings available</p>
      </div>
    )
  }

  // Check if settings were not captured for this mission
  if (settings?.comprehensive_settings?.settings_not_captured) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
        <Settings className="h-12 w-12 text-muted-foreground/50" />
        <div className="text-center space-y-2">
          <p className="text-lg font-medium text-muted-foreground">Settings Not Captured</p>
          <p className="text-sm text-muted-foreground max-w-md">
            {settings.comprehensive_settings.message || "Settings were not saved for this mission. This feature was added after this mission started."}
          </p>
          {(settings.comprehensive_settings.use_web_search || settings.comprehensive_settings.use_local_rag) && (
            <div className="mt-4 space-y-2">
              <p className="text-xs text-muted-foreground">Tool Selection:</p>
              <div className="flex gap-2 justify-center">
                {settings.comprehensive_settings.use_web_search && (
                  <Badge variant="outline" className="text-xs">Web Search</Badge>
                )}
                {settings.comprehensive_settings.use_local_rag && (
                  <Badge variant="outline" className="text-xs">Local RAG</Badge>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 p-4 overflow-y-auto max-h-full">
      {/* Mission Creation Settings */}
      {settings?.comprehensive_settings && (
        <Card className="border-primary/20">
          <CardHeader className="pb-3 bg-primary/5">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Mission Creation Settings
              {settings.comprehensive_settings.settings_captured_at && (
                <span className="text-xs text-muted-foreground ml-auto">
                  {new Date(settings.comprehensive_settings.settings_captured_at).toLocaleString()}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Web Search</span>
              <Badge variant={settings.comprehensive_settings.use_web_search ? 'default' : 'secondary'}>
                {settings.comprehensive_settings.use_web_search ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Local RAG</span>
              <Badge variant={settings.comprehensive_settings.use_local_rag ? 'default' : 'secondary'}>
                {settings.comprehensive_settings.use_local_rag ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
            {settings.comprehensive_settings.document_group_name && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Document Group</span>
                <Badge variant="outline">{settings.comprehensive_settings.document_group_name}</Badge>
              </div>
            )}
            {settings.comprehensive_settings.search_provider && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Search Provider</span>
                <Badge variant="outline">{settings.comprehensive_settings.search_provider}</Badge>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Model Configuration */}
      {settings?.comprehensive_settings?.model_config && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Brain className="h-4 w-4" />
              AI Models (At Mission Creation)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {settings.comprehensive_settings.model_config.fast_model && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Fast Model</span>
                <span className="text-sm font-mono">
                  {settings.comprehensive_settings.model_config.fast_provider}/{settings.comprehensive_settings.model_config.fast_model}
                </span>
              </div>
            )}
            {settings.comprehensive_settings.model_config.mid_model && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Mid Model</span>
                <span className="text-sm font-mono">
                  {settings.comprehensive_settings.model_config.mid_provider}/{settings.comprehensive_settings.model_config.mid_model}
                </span>
              </div>
            )}
            {settings.comprehensive_settings.model_config.intelligent_model && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Intelligent Model</span>
                <span className="text-sm font-mono">
                  {settings.comprehensive_settings.model_config.intelligent_provider}/{settings.comprehensive_settings.model_config.intelligent_model}
                </span>
              </div>
            )}
            {settings.comprehensive_settings.model_config.verifier_model && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Verifier Model</span>
                <span className="text-sm font-mono">
                  {settings.comprehensive_settings.model_config.verifier_provider}/{settings.comprehensive_settings.model_config.verifier_model}
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Research Parameters - Complete Settings */}
      {settings?.comprehensive_settings?.research_params && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Research Parameters Used
              {settings?.comprehensive_settings?.settings_captured_at_start && (
                <Badge variant="secondary" className="text-xs ml-auto">
                  <Clock className="h-3 w-3 mr-1" />
                  Captured at Start
                  {settings?.comprehensive_settings?.start_method === "chat_command" && " (Chat)"}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Research Configuration */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Research Configuration</h4>
              <div className="grid grid-cols-2 gap-2">
                {settings.comprehensive_settings.research_params.initial_research_max_depth !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Max Depth</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.initial_research_max_depth}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.initial_research_max_questions !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Max Questions</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.initial_research_max_questions}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.structured_research_rounds !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Research Rounds</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.structured_research_rounds}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.writing_passes !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Writing Passes</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.writing_passes}</Badge>
                  </div>
                )}
              </div>
            </div>

            {/* Search Results */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Search Results</h4>
              <div className="grid grid-cols-2 gap-2">
                {settings.comprehensive_settings.research_params.initial_exploration_doc_results !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Initial Docs</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.initial_exploration_doc_results}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.initial_exploration_web_results !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Initial Web</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.initial_exploration_web_results}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.main_research_doc_results !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Main Docs</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.main_research_doc_results}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.main_research_web_results !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Main Web</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.main_research_web_results}</Badge>
                  </div>
                )}
              </div>
            </div>

            {/* Performance & Options */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Performance & Options</h4>
              <div className="grid grid-cols-2 gap-2">
                {settings.comprehensive_settings.research_params.thought_pad_context_limit !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Context Limit</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.thought_pad_context_limit}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_notes_for_assignment_reranking !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Max Notes</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_notes_for_assignment_reranking}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_concurrent_requests !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Concurrent Reqs</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_concurrent_requests}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.skip_final_replanning !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Skip Replanning</span>
                    <Badge variant={settings.comprehensive_settings.research_params.skip_final_replanning ? 'default' : 'secondary'} className="text-xs">
                      {settings.comprehensive_settings.research_params.skip_final_replanning ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.auto_optimize_params !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Auto-Optimize</span>
                    <Badge variant={settings.comprehensive_settings.research_params.auto_optimize_params ? 'default' : 'secondary'} className="text-xs">
                      {settings.comprehensive_settings.research_params.auto_optimize_params ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                )}
              </div>
            </div>

            {/* Advanced Research Loop */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Advanced Research Loop</h4>
              <div className="grid grid-cols-2 gap-2">
                {settings.comprehensive_settings.research_params.max_research_cycles_per_section !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Cycles/Section</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_research_cycles_per_section}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_total_iterations !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Total Iterations</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_total_iterations}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_total_depth !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Max Outline Depth</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_total_depth}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_suggestions_per_batch !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Suggestions/Batch</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_suggestions_per_batch}</Badge>
                  </div>
                )}
              </div>
            </div>

            {/* Note Assignment Limits */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Note Assignment Limits</h4>
              <div className="grid grid-cols-2 gap-2">
                {settings.comprehensive_settings.research_params.min_notes_per_section_assignment !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Min Notes/Section</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.min_notes_per_section_assignment}</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.max_notes_per_section_assignment !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Max Notes/Section</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_notes_per_section_assignment}</Badge>
                  </div>
                )}
              </div>
            </div>

            {/* Content Processing Limits */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase">Content Processing Limits</h4>
              <div className="space-y-1">
                {settings.comprehensive_settings.research_params.max_planning_context_chars !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Planning Context</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.max_planning_context_chars.toLocaleString()} chars</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.writing_previous_content_preview_chars !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Writing Preview</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.writing_previous_content_preview_chars.toLocaleString()} chars</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.research_note_content_limit !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Note Content Limit</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.research_note_content_limit.toLocaleString()} chars</Badge>
                  </div>
                )}
                {settings.comprehensive_settings.research_params.writing_agent_max_context_chars !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Writing Agent Context</span>
                    <Badge variant="outline" className="text-xs">{settings.comprehensive_settings.research_params.writing_agent_max_context_chars.toLocaleString()} chars</Badge>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}


      {/* Mission-Specific Overrides */}
      {settings?.mission_specific_settings && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Settings className="h-4 w-4" />
              Mission-Specific Overrides
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs overflow-auto p-2 bg-secondary rounded max-h-40">
              {JSON.stringify(settings.mission_specific_settings, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Mission Status */}
      {mission && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Mission Status
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <Badge variant={
                mission.status === 'completed' ? 'default' :
                mission.status === 'running' ? 'secondary' :
                mission.status === 'failed' ? 'destructive' :
                'outline'
              }>
                {mission.status}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Created</span>
              <span className="text-sm">
                {new Date(mission.createdAt).toLocaleString()}
              </span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}