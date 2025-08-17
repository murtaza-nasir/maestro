import React from 'react';
import { Brain, FileText, Search, BookOpen, Lightbulb } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';
import { stringifyCleanLogData } from '../../utils/logUtils';
import { themeColors } from './themeColors';

interface ResearchAgentLogProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
}

export const ResearchAgentLog: React.FC<ResearchAgentLogProps> = ({ log, isExpanded }) => {
  if (!isExpanded) return null;

  const renderResearchOutput = () => {
    if (!log.full_output) return null;

    return (
      <div className="mb-4 space-y-4">
        {/* Research Summary Card */}
        <div className={`${themeColors.researchBg} ${themeColors.researchBorder} border rounded-lg p-4`}>
          <h4 className={`text-sm font-semibold ${themeColors.researchText} mb-3 flex items-center`}>
            <Search className="h-4 w-4 mr-2" />
            Research Summary
          </h4>
          
          {log.full_output.relevant_notes && (
            <div className="mb-3">
              <div className={`flex items-center text-xs ${themeColors.researchTextSecondary} mb-1`}>
                <BookOpen className="h-3 w-3 mr-1" />
                Relevant Notes Found
              </div>
              <div className={`text-lg font-bold ${themeColors.researchAccent}`}>
                {log.full_output.relevant_notes.length}
              </div>
            </div>
          )}
          
          {log.full_output.new_sub_questions && log.full_output.new_sub_questions.length > 0 && (
            <div className="mb-3">
              <div className={`flex items-center text-xs ${themeColors.successText} mb-2`}>
                <Lightbulb className="h-3 w-3 mr-1" />
                New Research Questions Generated
              </div>
              <div className="space-y-2">
                {log.full_output.new_sub_questions.map((question: string, index: number) => (
                  <div key={index} className={`text-sm ${themeColors.contentText} ${themeColors.contentCard} p-2 rounded border-l-2 ${themeColors.successAccent}`}>
                    {question}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Notes Analysis */}
        {log.full_output.relevant_notes && log.full_output.relevant_notes.length > 0 && (
          <div className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg p-4`}>
            <h4 className={`text-sm font-semibold ${themeColors.contentText} mb-3 flex items-center`}>
              <BookOpen className="h-4 w-4 mr-2" />
              Analyzed Notes
            </h4>
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {log.full_output.relevant_notes.map((note: any, index: number) => (
                <div key={index} className={`text-sm border ${themeColors.toolBorder} rounded p-3 ${themeColors.contentHover}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className={`text-xs font-mono ${themeColors.contentMuted}`}>Note ID: {note.note_id}</span>
                    <span className={`text-xs px-2 py-1 ${themeColors.badge} rounded`}>
                      {note.source_type}
                    </span>
                  </div>
                  <p className={`${themeColors.contentText} mb-2`}>{note.content}</p>
                  {note.source_metadata && (
                    <div className={`text-xs ${themeColors.contentMuted}`}>
                      Source: {note.source_metadata.title || note.source_id}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Scratchpad Update */}
        {log.full_output.updated_scratchpad && (
          <div className={`${themeColors.warningBg} ${themeColors.warningBorder} border rounded-lg p-4`}>
            <h4 className={`text-sm font-semibold ${themeColors.warningText} mb-2 flex items-center`}>
              <Brain className="h-4 w-4 mr-2" />
              Agent Scratchpad Update
            </h4>
            <div className={`text-sm ${themeColors.warningTextSecondary} ${themeColors.contentCard} p-3 rounded border-l-2 ${themeColors.warningAccent}`}>
              {log.full_output.updated_scratchpad}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderFileInteractions = () => {
    if (!log.file_interactions || log.file_interactions.length === 0) return null;

    return (
      <div className="mb-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
          <FileText className="h-4 w-4 mr-1" />
          File Operations
        </h4>
        <div className="bg-white border border-gray-200 rounded p-3">
          <ul className="text-sm space-y-1">
            {log.file_interactions.map((file, index) => (
              <li key={index} className="text-gray-700 font-mono text-xs p-2 bg-gray-50 rounded">
                {file}
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  };

  return (
    <div className="p-4 space-y-4">
      {renderResearchOutput()}
      <ToolCallsRenderer log={log} />
      {renderFileInteractions()}
      
      {log.full_output && (
        <details className="group">
          <summary className="text-sm font-semibold text-gray-700 cursor-pointer hover:text-gray-900">
            🔧 Raw Research Data
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
