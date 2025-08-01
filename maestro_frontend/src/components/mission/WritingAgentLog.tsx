import React from 'react';
import { PenTool, Edit3, BookOpen } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ToolCallsRenderer } from './ToolCallsRenderer';

interface WritingAgentLogProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
}

export const WritingAgentLog: React.FC<WritingAgentLogProps> = ({ log, isExpanded }) => {
  if (!isExpanded) return null;

  const renderWritingOutput = () => {
    if (!log.output_summary && !log.full_output) return null;

    const content = log.output_summary || (log.full_output && typeof log.full_output === 'string' ? log.full_output : null);
    
    if (!content) return null;

    return (
      <div className="mb-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
          <PenTool className="h-4 w-4 mr-1" />
          Generated Content
        </h4>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="prose prose-sm max-w-none">
            <div className="text-gray-800 whitespace-pre-wrap leading-relaxed">
              {content.split('\n').map((paragraph, index) => (
                paragraph.trim() === '' ? (
                  <br key={index} />
                ) : (
                  <p key={index} className="mb-3 last:mb-0">
                    {paragraph}
                  </p>
                )
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderWritingDetails = () => {
    if (!log.full_output || typeof log.full_output !== 'object') return null;

    const writingData = log.full_output;
    
    return (
      <div className="mb-4 space-y-4">
        {/* Writing Strategy */}
        {writingData.writing_approach && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-blue-800 mb-2 flex items-center">
              <Edit3 className="h-4 w-4 mr-2" />
              Writing Approach
            </h4>
            <div className="text-sm text-blue-700 bg-white p-3 rounded">
              {writingData.writing_approach}
            </div>
          </div>
        )}

        {/* Content Structure */}
        {writingData.content_structure && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <BookOpen className="h-4 w-4 mr-2" />
              Content Structure
            </h4>
            <div className="text-sm text-gray-700 space-y-2">
              {Array.isArray(writingData.content_structure) ? (
                <ul className="list-disc list-inside space-y-1">
                  {writingData.content_structure.map((item: string, index: number) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div>{writingData.content_structure}</div>
              )}
            </div>
          </div>
        )}

        {/* Key Points */}
        {writingData.key_points && writingData.key_points.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Key Points Addressed</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {writingData.key_points.map((point: string, index: number) => (
                <div key={index} className="text-sm text-gray-700 bg-gray-50 p-2 rounded border-l-2 border-gray-400">
                  {point}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Style Notes */}
        {writingData.style_notes && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-amber-800 mb-2">Style & Tone</h4>
            <div className="text-sm text-amber-700 bg-white p-3 rounded">
              {writingData.style_notes}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-4 space-y-4">
      {renderWritingOutput()}
      {renderWritingDetails()}
      <ToolCallsRenderer log={log} />
    </div>
  );
};
