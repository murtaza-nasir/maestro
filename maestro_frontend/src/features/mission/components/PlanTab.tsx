import React, { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '../../../components/ui/card'
import { Button } from '../../../components/ui/button'
import { useMissionStore } from '../store'
import { useToast } from '../../../components/ui/toast'
import { FileText, Target, RefreshCw } from 'lucide-react'
import { apiClient } from '../../../config/api'
import { UnifiedResumeModal } from './UnifiedResumeModal'

interface PlanTabProps {
  missionId: string
}

export const PlanTab: React.FC<PlanTabProps> = ({ missionId }) => {
  const { activeMission, setMissionPlan, missionLogs } = useMissionStore()
  const { addToast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [showUnifiedModal, setShowUnifiedModal] = useState(false)

  const fetchPlan = useCallback(async () => {
    if (!missionId) return
    try {
      const response = await apiClient.get(`/api/missions/${missionId}/plan`)
      if (response.data && response.data.plan) {
        useMissionStore.getState().setMissionPlan(missionId, JSON.stringify(response.data.plan, null, 2))
      }
    } catch (error) {
      console.error('Failed to fetch mission plan:', error)
    }
  }, [missionId])

  // Only fetch plan once when component mounts or missionId changes
  useEffect(() => {
    if (!activeMission?.plan) {
      fetchPlan()
    }
  }, [fetchPlan, activeMission?.plan])

  // WebSocket updates are now handled by ResearchPanel

  const handleOpenUnifiedModal = () => {
    setShowUnifiedModal(true)
  }

  const handleModalSuccess = () => {
    // Refresh the plan if needed
    fetchPlan()
  }

  const formatPlan = (plan: string) => {
    if (!plan) return ''
    
    // Try to parse as JSON first (in case it's structured data)
    try {
      const parsed = JSON.parse(plan)
      if (typeof parsed === 'object') {
        return parsed
      }
    } catch {
      // If not JSON, return as-is
    }
    
    return plan
  }

  const renderPlanContent = (plan: any) => {
    if (typeof plan === 'string') {
      return (
        <pre className="whitespace-pre-wrap text-sm text-foreground font-mono">
          {plan}
        </pre>
      )
    }

    if (typeof plan === 'object' && plan !== null) {
      return (
        <div className="space-y-6">
          {/* Mission Goal Card */}
          {plan.mission_goal && (
            <Card>
              <CardContent className="p-4">
                <div className="flex items-start space-x-3">
                  <Target className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
                  <div>
                    <h5 className="font-medium text-foreground mb-2 text-sm">Mission Goal</h5>
                    <p className="text-muted-foreground text-xs">{plan.mission_goal}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* Report Outline with Enhanced Cards */}
          {plan.report_outline && Array.isArray(plan.report_outline) && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h5 className="font-semibold text-foreground">Research Sections</h5>
                <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                  <span>{plan.report_outline.length} sections</span>
                  <span>•</span>
                  <span>
                    {(() => {
                      const countNotes = (sections: any[]): number => {
                        return sections.reduce((total: number, section: any) => {
                          let sectionTotal = section.associated_note_ids?.length || 0;
                          if (section.subsections && section.subsections.length > 0) {
                            sectionTotal += countNotes(section.subsections);
                          }
                          return total + sectionTotal;
                        }, 0);
                      };
                      return countNotes(plan.report_outline);
                    })()} total notes
                  </span>
                </div>
              </div>
              
              <div className="space-y-4">
                {plan.report_outline.map((section: any, index: number) => (
                  <Card key={index} className="border-l-4 border-l-primary">
                    <CardContent className="p-4">
                      <div className="space-y-3">
                        {/* Section Header */}
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h6 className="font-medium text-foreground text-sm">
                              {index + 1}. {section.title}
                            </h6>
                            {section.description && (
                              <p className="text-muted-foreground mt-1 text-xs">{section.description}</p>
                            )}
                          </div>
                        </div>

                        {/* Section Metadata */}
                        <div className="flex flex-wrap gap-2">
                          {/* Research Strategy Badge */}
                          {section.research_strategy && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
                              Strategy: {section.research_strategy?.replace('_', ' ') || section.research_strategy}
                            </span>
                          )}
                          
                          {/* Notes Count Badge */}
                          {section.associated_note_ids && section.associated_note_ids.length > 0 && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-500">
                              {section.associated_note_ids.length} notes
                            </span>
                          )}
                          
                          {/* Dependencies Badge */}
                          {section.depends_on_steps && section.depends_on_steps.length > 0 && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-500">
                              {section.depends_on_steps.length} dependencies
                            </span>
                          )}
                          
                          {/* Subsections Badge */}
                          {section.subsections && section.subsections.length > 0 && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-500/10 text-purple-500">
                              {section.subsections.length} subsections
                            </span>
                          )}
                        </div>

                        {/* Progress Indicator */}
                        {section.associated_note_ids && (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">Research Progress</span>
                              <span className="text-foreground font-medium">
                                {section.associated_note_ids.length} / {section.associated_note_ids.length} notes
                              </span>
                            </div>
                            <div className="w-full bg-secondary rounded-full h-2">
                              <div 
                                className="bg-primary h-2 rounded-full transition-all duration-300"
                                style={{ width: section.associated_note_ids.length > 0 ? '100%' : '0%' }}
                              ></div>
                            </div>
                          </div>
                        )}

                        {/* Subsections */}
                        {section.subsections && Array.isArray(section.subsections) && section.subsections.length > 0 && (
                          <div className="mt-4 space-y-2">
                            <div className="text-sm font-medium text-muted-foreground">Subsections:</div>
                            <div className="grid gap-2">
                              {section.subsections.map((subsection: any, subIndex: number) => (
                                <div key={subIndex} className="bg-secondary rounded-md p-3">
                                  <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                      <span className="font-medium text-foreground text-xs">
                                        {index + 1}.{subIndex + 1} {subsection.title}
                                      </span>
                                      {subsection.description && (
                                        <p className="text-muted-foreground text-xs mt-1">{subsection.description}</p>
                                      )}
                                    </div>
                                    {subsection.associated_note_ids && subsection.associated_note_ids.length > 0 && (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground ml-2 flex-shrink-0">
                                        {subsection.associated_note_ids.length} notes
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
          
          {/* Fallback to JSON display for any other structure */}
          {!plan.mission_goal && !plan.report_outline && (
            <Card>
              <CardContent className="p-4">
                <pre className="whitespace-pre-wrap text-sm text-foreground font-mono bg-secondary p-4 rounded-md overflow-auto">
                  {JSON.stringify(plan, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      )
    }

    return (
      <pre className="whitespace-pre-wrap text-sm text-foreground font-mono">
        {String(plan)}
      </pre>
    )
  }

  const getStatusInfo = () => {
    if (!activeMission) return { color: 'gray', text: 'No Mission' }
    
    switch (activeMission.status) {
      case 'pending':
        return { color: 'yellow', text: 'Planning' }
      case 'running':
        return { color: 'blue', text: 'In Progress' }
      case 'completed':
        return { color: 'green', text: 'Completed' }
      case 'failed':
        return { color: 'red', text: 'Failed' }
      case 'paused':
        return { color: 'orange', text: 'Paused' }
      case 'stopped':
        return { color: 'gray', text: 'Stopped' }
      default:
        return { color: 'gray', text: 'Unknown' }
    }
  }

  const statusInfo = getStatusInfo()

  return (
    <div className="flex flex-col h-full max-h-full overflow-hidden space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1">
            <FileText className="h-4 w-4 text-primary" />
            <h3 className="text-base font-semibold text-foreground">Research Plan</h3>
          </div>
          <div className="flex items-center space-x-1">
            <div className={`w-2 h-2 rounded-full bg-${statusInfo.color}-500`}></div>
            <span className="text-xs text-muted-foreground">{statusInfo.text}</span>
          </div>
        </div>
        
        <div className="flex items-center space-x-2">
          {/* Unified Restart/Revise button for all missions with a plan */}
          {activeMission?.plan && (
            <Button
              onClick={handleOpenUnifiedModal}
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={isLoading}
              title="Restart or revise research mission"
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              Restart / Revise
            </Button>
          )}
        </div>
      </div>

      {/* Plan Content */}
      <Card className="flex-1 overflow-hidden">
        <CardContent className="p-0 h-full flex flex-col">
          <div className="h-full flex flex-col">
            {activeMission?.plan ? (
              <div className="flex-1 overflow-hidden">
                <div className="h-full overflow-y-auto p-3">
                  {renderPlanContent(formatPlan(activeMission.plan))}
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center text-muted-foreground">
                  <FileText className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm font-medium mb-1">No Plan Available</p>
                  <p className="text-xs">
                    {activeMission?.status === 'pending' 
                      ? 'The research plan is being generated...'
                      : 'Start a research mission to see the plan here.'
                    }
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      
      {/* Unified Resume/Revise Modal */}
      {showUnifiedModal && (
        <UnifiedResumeModal
          isOpen={showUnifiedModal}
          onClose={() => setShowUnifiedModal(false)}
          missionId={missionId}
          onSuccess={handleModalSuccess}
        />
      )}
    </div>
  )
}
