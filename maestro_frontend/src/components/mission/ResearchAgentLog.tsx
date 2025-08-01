import React from 'react';
import { Brain, FileText, Search, BookOpen, Lightbulb } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';
import { stringifyCleanLogData } from '../../utils/logUtils';

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
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-blue-800 mb-3 flex items-center">
            <Search className="h-4 w-4 mr-2" />
            Research Summary
          </h4>
          
          {log.full_output.relevant_notes && (
            <div className="mb-3">
              <div className="flex items-center text-xs text-blue-600 mb-1">
                <BookOpen className="h-3 w-3 mr-1" />
                Relevant Notes Found
              </div>
              <div className="text-lg font-bold text-blue-700">
                {log.full_output.relevant_notes.length}
              </div>
            </div>
          )}
          
          {log.full_output.new_sub_questions && log.full_output.new_sub_questions.length > 0 && (
            <div className="mb-3">
              <div className="flex items-center text-xs text-green-600 mb-2">
                <Lightbulb className="h-3 w-3 mr-1" />
                New Research Questions Generated
              </div>
              <div className="space-y-2">
                {log.full_output.new_sub_questions.map((question: string, index: number) => (
                  <div key={index} className="text-sm text-gray-700 bg-white p-2 rounded border-l-2 border-green-400">
                    {question}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Notes Analysis */}
        {log.full_output.relevant_notes && log.full_output.relevant_notes.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <BookOpen className="h-4 w-4 mr-2" />
              Analyzed Notes
            </h4>
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {log.full_output.relevant_notes.map((note: any, index: number) => (
                <div key={index} className="text-sm border border-gray-100 rounded p-3 hover:bg-gray-50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono text-gray-500">Note ID: {note.note_id}</span>
                    <span className="text-xs px-2 py-1 bg-gray-100 rounded">
                      {note.source_type}
                    </span>
                  </div>
                  <p className="text-gray-700 mb-2">{note.content}</p>
                  {note.source_metadata && (
                    <div className="text-xs text-gray-500">
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
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-amber-800 mb-2 flex items-center">
              <Brain className="h-4 w-4 mr-2" />
              Agent Scratchpad Update
            </h4>
            <div className="text-sm text-amber-700 bg-white p-3 rounded border-l-2 border-amber-400">
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
