import React from 'react';
import { Eye, MessageSquare, CheckCircle, AlertTriangle, BarChart3, Lightbulb, Target, FileText, Search } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';

interface ReflectionAgentLogProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
}

export const ReflectionAgentLog: React.FC<ReflectionAgentLogProps> = ({ log, isExpanded }) => {
  if (!isExpanded) return null;

  const renderReflectionOutput = () => {
    if (!log.full_output) return null;

    const reflectionData = log.full_output;

    return (
      <div className="mb-4 space-y-4">
        {/* Overall Assessment Card */}
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-amber-800 mb-3 flex items-center">
            <Eye className="h-4 w-4 mr-2" />
            Reflection Analysis
          </h4>
          
          {reflectionData.overall_assessment && (
            <div className="mb-3">
              <div className="flex items-center text-xs text-amber-600 mb-1">
                <BarChart3 className="h-3 w-3 mr-1" />
                Overall Assessment
              </div>
              <div className="text-sm text-gray-700 bg-white p-3 rounded border-l-2 border-amber-400">
                {reflectionData.overall_assessment}
              </div>
            </div>
          )}

          {/* Quality Score */}
          {reflectionData.overall_score !== undefined && (
            <div className="mb-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center text-xs text-gray-600">
                  <BarChart3 className="h-3 w-3 mr-1" />
                  Quality Score
                </div>
                <div className="text-lg font-bold text-blue-600">
                  {reflectionData.overall_score}/10
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-gradient-to-r from-amber-400 to-orange-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${(reflectionData.overall_score / 10) * 100}%` }}
                />
              </div>
            </div>
          )}

          {reflectionData.generated_thought && (
            <div>
              <div className="flex items-center text-xs text-purple-600 mb-1">
                <Lightbulb className="h-3 w-3 mr-1" />
                Strategic Insight
              </div>
              <div className="text-sm text-purple-700 bg-purple-50 p-3 rounded border-l-2 border-purple-400">
                {reflectionData.generated_thought}
              </div>
            </div>
          )}
        </div>

        {/* Strengths and Weaknesses */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Strengths */}
          {reflectionData.strengths && reflectionData.strengths.length > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-green-800 mb-2 flex items-center">
                <CheckCircle className="h-4 w-4 mr-2" />
                Key Strengths
              </h4>
              <ul className="text-sm space-y-2">
                {reflectionData.strengths.map((strength: string, index: number) => (
                  <li key={index} className="text-green-700 flex items-start">
                    <CheckCircle className="h-4 w-4 mr-2 text-green-500 flex-shrink-0 mt-0.5" />
                    <span>{strength}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Areas for Improvement */}
          {reflectionData.weaknesses && reflectionData.weaknesses.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-amber-800 mb-2 flex items-center">
                <AlertTriangle className="h-4 w-4 mr-2" />
                Areas for Improvement
              </h4>
              <ul className="text-sm space-y-2">
                {reflectionData.weaknesses.map((weakness: string, index: number) => (
                  <li key={index} className="text-amber-700 flex items-start">
                    <AlertTriangle className="h-4 w-4 mr-2 text-amber-500 flex-shrink-0 mt-0.5" />
                    <span>{weakness}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Research Guidance */}
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
            <Search className="h-4 w-4 mr-2" />
            Research Guidance
          </h4>
          
          {/* New Questions */}
          {reflectionData.new_questions && reflectionData.new_questions.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center text-xs text-blue-600 mb-2">
                <Target className="h-3 w-3 mr-1" />
                Next Research Questions
              </div>
              <div className="space-y-2">
                {reflectionData.new_questions.map((question: string, index: number) => (
                  <div key={index} className="text-sm text-gray-700 bg-blue-50 p-3 rounded border-l-2 border-blue-400">
                    {question}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {reflectionData.recommendations && reflectionData.recommendations.length > 0 && (
            <div>
              <div className="flex items-center text-xs text-purple-600 mb-2">
                <MessageSquare className="h-3 w-3 mr-1" />
                Action Recommendations
              </div>
              <div className="space-y-2">
                {reflectionData.recommendations.map((recommendation: string, index: number) => (
                  <div key={index} className="text-sm text-gray-700 bg-purple-50 p-3 rounded border-l-2 border-purple-400">
                    {recommendation}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Subsection Suggestions */}
        {reflectionData.suggested_subsection_topics && reflectionData.suggested_subsection_topics.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <FileText className="h-4 w-4 mr-2" />
              Suggested Subsections
            </h4>
            <div className="space-y-3">
              {reflectionData.suggested_subsection_topics.map((topic: any, index: number) => (
                <div key={index} className="border border-gray-100 rounded p-3 hover:bg-gray-50">
                  <div className="font-medium text-gray-900 mb-1">{topic.title}</div>
                  <div className="text-sm text-gray-600 mb-2">{topic.description}</div>
                  {topic.reasoning && (
                    <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded">
                      <span className="font-medium">Reasoning:</span> {topic.reasoning}
                    </div>
                  )}
                  {topic.relevant_note_ids && topic.relevant_note_ids.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs text-gray-500 mb-1">Relevant Notes:</div>
                      <div className="flex flex-wrap gap-1">
                        {topic.relevant_note_ids.map((noteId: string, noteIndex: number) => (
                          <span key={noteIndex} className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded">
                            {noteId}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Critical Issues */}
        {reflectionData.critical_issues_summary && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-red-800 mb-2 flex items-center">
              <AlertTriangle className="h-4 w-4 mr-2" />
              Critical Issues Identified
            </h4>
            <div className="text-sm text-red-700 bg-white p-3 rounded">
              {reflectionData.critical_issues_summary}
            </div>
          </div>
        )}

        {/* Notes to Discard */}
        {reflectionData.discard_note_ids && reflectionData.discard_note_ids.length > 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <FileText className="h-4 w-4 mr-2" />
              Notes Marked for Discard
            </h4>
            <div className="flex flex-wrap gap-2">
              {reflectionData.discard_note_ids.map((noteId: string, index: number) => (
                <span key={index} className="text-xs px-2 py-1 bg-red-100 text-red-800 rounded line-through">
                  {noteId}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-4 space-y-4">
      {renderReflectionOutput()}
      <ToolCallsRenderer log={log} />
    </div>
  );
};
