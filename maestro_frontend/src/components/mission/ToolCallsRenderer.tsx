import React, { useState } from 'react';
import { Settings, Search, ChevronDown, ChevronRight, CheckCircle, XCircle } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { themeColors } from './themeColors';

interface ToolCallsRendererProps {
  log: ExecutionLogEntry;
}

interface GroupedToolCall {
  tool_name: string;
  calls: any[];
  status: string;
  totalResults?: number;
}

export const ToolCallsRenderer: React.FC<ToolCallsRendererProps> = ({ log }) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  if (!log.tool_calls || log.tool_calls.length === 0) return null;

  // Group tool calls by tool name
  const groupedCalls = log.tool_calls.reduce((groups: Record<string, GroupedToolCall>, tool) => {
    if (!groups[tool.tool_name]) {
      groups[tool.tool_name] = {
        tool_name: tool.tool_name,
        calls: [],
        status: 'success',
        totalResults: 0
      };
    }
    
    groups[tool.tool_name].calls.push(tool);
    
    // Update status - if any call failed, mark group as failed
    if (tool.error) {
      groups[tool.tool_name].status = 'failed';
    }
    
    // Count total results for document searches
    if (tool.tool_name === 'document_search' && tool.result_summary) {
      const match = tool.result_summary.match(/(\d+) results found/);
      if (match) {
        groups[tool.tool_name].totalResults! += parseInt(match[1]);
      }
    }
    
    return groups;
  }, {});

  const toggleGroup = (toolName: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(toolName)) {
      newExpanded.delete(toolName);
    } else {
      newExpanded.add(toolName);
    }
    setExpandedGroups(newExpanded);
  };

  const getToolIcon = (toolName: string) => {
    if (toolName.includes('search')) return <Search className="h-4 w-4" />;
    return <Settings className="h-4 w-4" />;
  };

  const getStatusIcon = (status: string) => {
    return status === 'failed' ? 
      <XCircle className="h-4 w-4 text-red-500" /> : 
      <CheckCircle className="h-4 w-4 text-green-500" />;
  };

  const renderGroupSummary = (group: GroupedToolCall) => {
    const isExpanded = expandedGroups.has(group.tool_name);
    
    return (
      <div key={group.tool_name} className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded-lg`}>
        {/* Group Header */}
        <div 
          className={`flex items-center justify-between p-3 cursor-pointer ${themeColors.contentHover}`}
          onClick={() => toggleGroup(group.tool_name)}
        >
          <div className="flex items-center space-x-2">
            {isExpanded ? 
              <ChevronDown className="h-4 w-4 text-muted-foreground" /> : 
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            }
            {getToolIcon(group.tool_name)}
            <span className={`font-medium ${themeColors.textPrimary}`}>{group.tool_name}</span>
            <span className={`text-sm ${themeColors.textSecondary}`}>({group.calls.length})</span>
          </div>
          
          <div className="flex items-center space-x-2">
            {/* Show summary for document searches */}
            {group.tool_name === 'document_search' && group.totalResults! > 0 && (
              <span className={`text-xs ${themeColors.researchBg} ${themeColors.researchText} px-2 py-1 rounded`}>
                {group.totalResults} total results
              </span>
            )}
            {getStatusIcon(group.status)}
          </div>
        </div>

        {/* Expanded Content */}
        {isExpanded && (
          <div className={`border-t ${themeColors.toolBorder} p-3 ${themeColors.toolBg}`}>
            {group.tool_name === 'document_search' ? 
              renderDocumentSearchGroup(group) : 
              renderGenericToolGroup(group)
            }
          </div>
        )}
      </div>
    );
  };

  const renderDocumentSearchGroup = (group: GroupedToolCall) => {
    return (
      <div className="space-y-3">
        {/* Search Queries Summary */}
        <div>
          <h5 className={`text-sm font-medium ${themeColors.contentText} mb-2`}>Search Queries:</h5>
          <div className="space-y-2">
            {group.calls.map((call, index) => (
              <div key={index} className={`${themeColors.contentCard} ${themeColors.contentBorder} border rounded p-2`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className={`text-xs ${themeColors.textPrimary} mb-1`}>
                      <span className="font-medium">Query:</span> {call.arguments?.query || 'N/A'}
                    </div>
                    <div className={`text-xs ${themeColors.textSecondary}`}>
                      Results: {call.arguments?.n_results || 'N/A'} | 
                      Reranker: {call.arguments?.use_reranker ? 'Yes' : 'No'}
                    </div>
                  </div>
                  <div className={`text-xs ${themeColors.contentMuted} ml-2`}>
                    {call.result_summary || 'No result'}
                  </div>
                </div>
                {call.error && (
                  <div className={`mt-2 text-xs p-2 rounded ${
                    call.error_type === 'access_denied' ? 'text-yellow-700 dark:text-yellow-300 bg-yellow-50 dark:bg-yellow-950/20' :
                    call.error_type === 'not_found' ? 'text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-950/20' :
                    call.error_type === 'timeout' ? 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/20' :
                    'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20'
                  }`}>
                    <span className="font-medium">
                      {call.error_type === 'access_denied' ? 'Access Restricted:' :
                       call.error_type === 'not_found' ? 'Not Found:' :
                       call.error_type === 'timeout' ? 'Timeout:' :
                       'Error:'}
                    </span> {call.error}
                    {call.suggestion && (
                      <div className="mt-1 text-xs opacity-80">
                        💡 {call.suggestion}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const renderGenericToolGroup = (group: GroupedToolCall) => {
    return (
      <div className="space-y-2">
        {group.calls.map((call, index) => (
          <div key={index} className="bg-white border border-gray-200 rounded p-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-800">Call {index + 1}</span>
              <span className={`text-xs px-2 py-1 rounded ${
                call.error ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
              }`}>
                {call.error ? 'Failed' : 'Success'}
              </span>
            </div>
            
            {call.arguments && Object.keys(call.arguments).length > 0 && (
              <div className="mb-2">
                <div className="text-xs text-gray-600 mb-1">Arguments:</div>
                <div className="space-y-1">
                  {Object.entries(call.arguments)
                    .filter(([key]) => !['update_callback', 'log_queue', 'filepath', 'allowed_base_path', 'feedback_callback'].includes(key))
                    .map(([key, value]) => (
                    <div key={key} className="bg-gray-50 p-2 rounded">
                      <div className="text-xs">
                        <span className="font-medium text-blue-600">{key}:</span>
                        <div className="mt-1 text-gray-800 break-words">
                          {typeof value === 'string' && value.length > 200 
                            ? `${value.substring(0, 200)}...` 
                            : String(value)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <div className="text-xs text-gray-700">
              <span className="font-medium">Result:</span> {call.result_summary || 'No result'}
            </div>
            
            {call.error && (
              <div className={`mt-2 text-xs p-2 rounded ${
                call.error_type === 'access_denied' ? 'text-yellow-700 bg-yellow-50' :
                call.error_type === 'not_found' ? 'text-orange-700 bg-orange-50' :
                call.error_type === 'timeout' ? 'text-blue-700 bg-blue-50' :
                'text-red-600 bg-red-50'
              }`}>
                <span className="font-medium">
                  {call.error_type === 'access_denied' ? 'Access Restricted:' :
                   call.error_type === 'not_found' ? 'Not Found:' :
                   call.error_type === 'timeout' ? 'Timeout:' :
                   'Error:'}
                </span> {call.error}
                {call.suggestion && (
                  <div className="mt-1 text-xs opacity-80">
                    💡 {call.suggestion}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const groups = Object.values(groupedCalls);

  return (
    <div className="mb-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
        <Settings className="h-4 w-4 mr-1" />
        Tool Calls ({log.tool_calls.length})
      </h4>
      <div className="space-y-2">
        {groups.map(renderGroupSummary)}
      </div>
    </div>
  );
};
