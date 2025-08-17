import React from 'react';
import { Target, Users, MapPin, List, Clock, CheckSquare } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';
import { stringifyCleanLogData } from '../../utils/logUtils';
import { themeColors } from './themeColors';

interface PlanningAgentLogProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
}

export const PlanningAgentLog: React.FC<PlanningAgentLogProps> = ({ log, isExpanded }) => {
  if (!isExpanded) return null;

  const renderPlanningOutput = () => {
    if (!log.full_output) return null;

    return (
      <div className="mb-4 space-y-4">
        {/* Mission Overview Card */}
        <div className={`${themeColors.planningBg} ${themeColors.planningBorder} border rounded-lg p-4`}>
          <h4 className={`text-sm font-semibold ${themeColors.planningText} mb-3 flex items-center`}>
            <Target className="h-4 w-4 mr-2" />
            Research Mission Overview
          </h4>
          
          {log.full_output.mission_goal && (
            <div className="mb-3">
              <div className={`flex items-center text-xs ${themeColors.planningAccent} mb-1`}>
                <Target className="h-3 w-3 mr-1" />
                Mission Objective
              </div>
              <div className={`text-sm ${themeColors.contentText} ${themeColors.contentCard} p-3 rounded border-l-2 ${themeColors.planningBorder}`}>
                {log.full_output.mission_goal}
              </div>
            </div>
          )}

          {log.full_output.generated_thought && (
            <div className="mb-3">
              <div className={`flex items-center text-xs ${themeColors.warningTextSecondary} mb-1`}>
                <Users className="h-3 w-3 mr-1" />
                Planning Insight
              </div>
              <div className={`text-sm ${themeColors.warningTextSecondary} ${themeColors.warningBg} p-3 rounded border-l-2 ${themeColors.warningAccent}`}>
                {log.full_output.generated_thought}
              </div>
            </div>
          )}
        </div>

        {/* Report Outline */}
        {log.full_output.report_outline && log.full_output.report_outline.length > 0 && (
          <div className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg p-4`}>
            <h4 className={`text-sm font-semibold ${themeColors.contentText} mb-3 flex items-center`}>
              <MapPin className="h-4 w-4 mr-2" />
              Research Report Structure
            </h4>
            <div className="space-y-3">
              {log.full_output.report_outline.map((section: any, index: number) => (
                <div key={index} className={`border ${themeColors.toolBorder} rounded p-3 ${themeColors.contentHover}`}>
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className={`font-medium ${themeColors.textPrimary}`}>{section.title}</div>
                      <div className={`text-xs ${themeColors.contentMuted} font-mono`}>ID: {section.section_id}</div>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded ${
                      section.research_strategy === 'research_based' ? `${themeColors.researchBg} ${themeColors.researchText}` :
                      section.research_strategy === 'content_based' ? `${themeColors.successBg} ${themeColors.successText}` :
                      `${themeColors.planningBg} ${themeColors.planningText}`
                    }`}>
                      {section.research_strategy?.replace('_', ' ') || section.research_strategy}
                    </span>
                  </div>
                  
                  {section.description && (
                    <div className={`text-sm ${themeColors.textSecondary} mb-2 ${themeColors.bgMuted} p-2 rounded`}>
                      {section.description}
                    </div>
                  )}
                  
                  {section.subsections && section.subsections.length > 0 && (
                    <div className="ml-4 mt-2 space-y-2">
                      {section.subsections.map((subsection: any, subIndex: number) => (
                        <div key={subIndex} className="border-l-2 border-gray-200 pl-3">
                          <div className="flex items-start justify-between">
                            <div>
                              <div className={`text-sm font-medium ${themeColors.textPrimary}`}>{subsection.title}</div>
                              <div className={`text-xs ${themeColors.contentMuted} font-mono`}>ID: {subsection.section_id}</div>
                            </div>
                            <span className={`text-xs px-2 py-1 rounded ${
                              subsection.research_strategy === 'research_based' ? `${themeColors.researchBg} ${themeColors.researchText}` :
                              subsection.research_strategy === 'content_based' ? `${themeColors.successBg} ${themeColors.successText}` :
                              `${themeColors.planningBg} ${themeColors.planningText}`
                            }`}>
                              {subsection.research_strategy?.replace('_', ' ') || subsection.research_strategy}
                            </span>
                          </div>
                          {subsection.description && (
                            <div className={`text-xs ${themeColors.textSecondary} mt-1 ${themeColors.toolBg} p-2 rounded`}>
                              {subsection.description}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Research Questions */}
        {log.full_output.research_questions && log.full_output.research_questions.length > 0 && (
          <div className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg p-4`}>
            <h4 className={`text-sm font-semibold ${themeColors.contentText} mb-3 flex items-center`}>
              <List className="h-4 w-4 mr-2" />
              Key Research Questions
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {log.full_output.research_questions.map((question: string, index: number) => (
                <div key={index} className={`text-sm ${themeColors.contentText} ${themeColors.researchBg} p-3 rounded border-l-2 border-blue-400 dark:border-blue-600`}>
                  {question}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Timeline and Criteria */}
        {(log.full_output.estimated_timeline || log.full_output.success_criteria) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {log.full_output.estimated_timeline && (
              <div className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg p-4`}>
                <h4 className={`text-sm font-semibold ${themeColors.contentText} mb-2 flex items-center`}>
                  <Clock className="h-4 w-4 mr-2" />
                  Estimated Timeline
                </h4>
                <div className={`text-sm ${themeColors.contentText} ${themeColors.researchBg} p-3 rounded`}>
                  {log.full_output.estimated_timeline}
                </div>
              </div>
            )}
            
            {log.full_output.success_criteria && log.full_output.success_criteria.length > 0 && (
              <div className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg p-4`}>
                <h4 className={`text-sm font-semibold ${themeColors.contentText} mb-2 flex items-center`}>
                  <CheckSquare className="h-4 w-4 mr-2" />
                  Success Criteria
                </h4>
                <ul className="text-sm space-y-1">
                  {log.full_output.success_criteria.map((criteria: string, index: number) => (
                    <li key={index} className={`${themeColors.contentText} flex items-start`}>
                      <span className="text-green-500 mr-2">✓</span>
                      {criteria}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-4 space-y-4">
      {renderPlanningOutput()}
      <ToolCallsRenderer log={log} />
      
      {log.full_output && (
        <details className="group">
          <summary className={`text-sm font-semibold ${themeColors.contentText} cursor-pointer hover:text-foreground`}>
            📊 Raw Planning Data
          </summary>
          <div className={`mt-2 ${themeColors.codeBg} p-3 rounded`}>
            <pre className="text-xs overflow-x-auto max-h-64 overflow-y-auto">
              {stringifyCleanLogData(log.full_output, 2)}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
};
