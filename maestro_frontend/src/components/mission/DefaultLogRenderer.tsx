import React from 'react';
import { FileText, Database, Code } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { stringifyCleanLogData } from '../../utils/logUtils';
import { ToolCallsRenderer } from './ToolCallsRenderer';

interface DefaultLogRendererProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
}

export const DefaultLogRenderer: React.FC<DefaultLogRendererProps> = ({ log, isExpanded }) => {
  if (!isExpanded) return null;

  const renderStructuredData = () => {
    if (!log.full_output && !log.full_input) return null;

    return (
      <div className="mb-4 space-y-4">
        {/* Output Data */}
        {log.full_output && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center">
              <Database className="h-3 w-3 mr-1" />
              Processed Output
            </h4>
            
            {typeof log.full_output === 'string' ? (
              <div className="text-sm text-gray-700 bg-gray-50 p-3 rounded">
                {log.full_output}
              </div>
            ) : Array.isArray(log.full_output) ? (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {log.full_output.map((item: any, index: number) => (
                  <div key={index} className="text-sm border border-gray-100 rounded p-3 hover:bg-gray-50">
                    {typeof item === 'object' ? (
                      <pre className="text-xs overflow-x-auto whitespace-pre-wrap break-words">
                        {stringifyCleanLogData(item, 2)}
                      </pre>
                    ) : (
                      <div className="text-gray-700">{String(item)}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : typeof log.full_output === 'object' ? (
              <div className="space-y-3">
                {Object.entries(log.full_output).map(([key, value]) => (
                  <div key={key} className="border border-gray-100 rounded p-3">
                    <div className="text-xs font-medium text-gray-500 mb-1 uppercase">
                      {key?.replace(/_/g, ' ') || key}
                    </div>
                    {typeof value === 'string' ? (
                      <div className="text-sm text-gray-700">{value}</div>
                    ) : Array.isArray(value) ? (
                      <div className="text-sm space-y-1">
                        {value.map((item: any, index: number) => (
                          <div key={index} className="bg-gray-50 p-2 rounded">
                            {typeof item === 'object' ? (
                              <pre className="text-xs overflow-x-auto">
                                {stringifyCleanLogData(item, 2)}
                              </pre>
                            ) : (
                              <div className="text-gray-700">{String(item)}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : typeof value === 'object' ? (
                      <pre className="text-xs overflow-x-auto bg-gray-50 p-2 rounded">
                        {stringifyCleanLogData(value, 2)}
                      </pre>
                    ) : (
                      <div className="text-sm text-gray-700">{String(value)}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-700 bg-gray-50 p-3 rounded">
                {String(log.full_output)}
              </div>
            )}
          </div>
        )}

        {/* Input Data */}
        {log.full_input && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center">
              <FileText className="h-3 w-3 mr-1" />
              Input Context
            </h4>
            
            {typeof log.full_input === 'string' ? (
              <div className="text-sm text-gray-700 bg-gray-50 p-3 rounded whitespace-pre-wrap">
                {log.full_input}
              </div>
            ) : (
              <pre className="text-xs overflow-x-auto bg-gray-50 p-3 rounded max-h-64 overflow-y-auto">
                {stringifyCleanLogData(log.full_input, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-4 space-y-4">
      <ToolCallsRenderer log={log} />
      {renderStructuredData()}
      
      {/* Raw Data Sections */}
      <div className="space-y-3">
        {/* Raw Output */}
        {log.full_output && (
          <details className="group">
            <summary className="text-sm font-semibold text-gray-700 cursor-pointer hover:text-gray-900 flex items-center">
              <Code className="h-4 w-4 mr-2" />
              📄 Raw Output Data
            </summary>
            <div className="mt-2 bg-gray-100 p-3 rounded">
              <pre className="text-xs overflow-x-auto max-h-64 overflow-y-auto">
                {stringifyCleanLogData(log.full_output, 2)}
              </pre>
            </div>
          </details>
        )}
        
        {/* Raw Input */}
        {log.full_input && (
          <details className="group">
            <summary className="text-sm font-semibold text-gray-700 cursor-pointer hover:text-gray-900 flex items-center">
              <Code className="h-4 w-4 mr-2" />
              📥 Raw Input Data
            </summary>
            <div className="mt-2 bg-gray-100 p-3 rounded">
              <pre className="text-xs overflow-x-auto max-h-64 overflow-y-auto">
                {stringifyCleanLogData(log.full_input, 2)}
              </pre>
            </div>
          </details>
        )}
      </div>
    </div>
  );
};
