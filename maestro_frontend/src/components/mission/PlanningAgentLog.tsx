import React from 'react';
import { Target, Users, MapPin, List, Clock, CheckSquare } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';
import { stringifyCleanLogData } from '../../utils/logUtils';

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
        <div className="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-purple-800 mb-3 flex items-center">
            <Target className="h-4 w-4 mr-2" />
            Research Mission Overview
          </h4>
          
          {log.full_output.mission_goal && (
            <div className="mb-3">
              <div className="flex items-center text-xs text-purple-600 mb-1">
                <Target className="h-3 w-3 mr-1" />
                Mission Objective
              </div>
              <div className="text-sm text-gray-700 bg-white p-3 rounded border-l-2 border-purple-400">
                {log.full_output.mission_goal}
              </div>
            </div>
          )}

          {log.full_output.generated_thought && (
            <div className="mb-3">
              <div className="flex items-center text-xs text-amber-600 mb-1">
                <Users className="h-3 w-3 mr-1" />
                Planning Insight
              </div>
              <div className="text-sm text-amber-700 bg-amber-50 p-3 rounded border-l-2 border-amber-400">
                {log.full_output.generated_thought}
              </div>
            </div>
          )}
        </div>

        {/* Report Outline */}
        {log.full_output.report_outline && log.full_output.report_outline.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <MapPin className="h-4 w-4 mr-2" />
              Research Report Structure
            </h4>
            <div className="space-y-3">
              {log.full_output.report_outline.map((section: any, index: number) => (
                <div key={index} className="border border-gray-100 rounded p-3 hover:bg-gray-50">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="font-medium text-gray-900">{section.title}</div>
                      <div className="text-xs text-gray-500 font-mono">ID: {section.section_id}</div>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded ${
                      section.research_strategy === 'research_based' ? 'bg-blue-100 text-blue-800' :
                      section.research_strategy === 'content_based' ? 'bg-green-100 text-green-800' :
                      'bg-purple-100 text-purple-800'
                    }`}>
                      {section.research_strategy?.replace('_', ' ') || section.research_strategy}
                    </span>
                  </div>
                  
                  {section.description && (
                    <div className="text-sm text-gray-600 mb-2 bg-gray-50 p-2 rounded">
                      {section.description}
                    </div>
                  )}
                  
                  {section.subsections && section.subsections.length > 0 && (
                    <div className="ml-4 mt-2 space-y-2">
                      {section.subsections.map((subsection: any, subIndex: number) => (
                        <div key={subIndex} className="border-l-2 border-gray-200 pl-3">
                          <div className="flex items-start justify-between">
                            <div>
                              <div className="text-sm font-medium text-gray-800">{subsection.title}</div>
                              <div className="text-xs text-gray-500 font-mono">ID: {subsection.section_id}</div>
                            </div>
                            <span className={`text-xs px-2 py-1 rounded ${
                              subsection.research_strategy === 'research_based' ? 'bg-blue-100 text-blue-800' :
                              subsection.research_strategy === 'content_based' ? 'bg-green-100 text-green-800' :
                              'bg-purple-100 text-purple-800'
                            }`}>
                              {subsection.research_strategy?.replace('_', ' ') || subsection.research_strategy}
                            </span>
                          </div>
                          {subsection.description && (
                            <div className="text-xs text-gray-600 mt-1 bg-gray-50 p-2 rounded">
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
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <List className="h-4 w-4 mr-2" />
              Key Research Questions
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {log.full_output.research_questions.map((question: string, index: number) => (
                <div key={index} className="text-sm text-gray-700 bg-blue-50 p-3 rounded border-l-2 border-blue-400">
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
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
                  <Clock className="h-4 w-4 mr-2" />
                  Estimated Timeline
                </h4>
                <div className="text-sm text-gray-700 bg-blue-50 p-3 rounded">
                  {log.full_output.estimated_timeline}
                </div>
              </div>
            )}
            
            {log.full_output.success_criteria && log.full_output.success_criteria.length > 0 && (
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
                  <CheckSquare className="h-4 w-4 mr-2" />
                  Success Criteria
                </h4>
                <ul className="text-sm space-y-1">
                  {log.full_output.success_criteria.map((criteria: string, index: number) => (
                    <li key={index} className="text-gray-700 flex items-start">
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
          <summary className="text-sm font-semibold text-gray-700 cursor-pointer hover:text-gray-900">
            📊 Raw Planning Data
          </summary>
          <div className="mt-2 bg-gray-100 p-3 rounded">
            <pre className="text-xs overflow-x-auto max-h-64 overflow-y-auto">
              {stringifyCleanLogData(log.full_output, 2)}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
};
