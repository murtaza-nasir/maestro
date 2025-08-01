import React from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ActionParser } from './ActionParser';
import { formatActivityLogTime } from '../../utils/timezone';

interface LogEntryCardProps {
  log: ExecutionLogEntry;
  isExpanded: boolean;
  onToggleExpansion: () => void;
  children: React.ReactNode;
}

export const LogEntryCard: React.FC<LogEntryCardProps> = ({
  log,
  isExpanded,
  onToggleExpansion,
  children
}) => {
  // Removed redundant status icons since we have colored side indicators

  const getAgentTypeIcon = (agentName: string) => {
    const name = agentName.toLowerCase();
    if (name.includes('planning')) return '📋';
    if (name.includes('research')) return '🔍';
    if (name.includes('writing')) return '✍️';
    if (name.includes('reflection')) return '🤔';
    if (name.includes('messenger')) return '💬';
    if (name.includes('user')) return '👤';
    if (name.includes('controller')) return '⚙️';
    if (name.includes('assignment')) return '📝';
    return '🤖';
  };

  const getStatusBorderColor = (status: ExecutionLogEntry['status']) => {
    switch (status) {
      case 'success':
        return 'border-l-green-500';
      case 'failure':
        return 'border-l-destructive';
      case 'running':
        return 'border-l-primary';
      case 'warning':
        return 'border-l-yellow-500';
      default:
        return 'border-l-muted';
    }
  };

  return (
    <div className={`bg-card border border-border rounded-lg shadow-sm hover:shadow-md transition-all duration-200 mb-2 overflow-hidden border-l-4 ${getStatusBorderColor(log.status)}`}>
      {/* Header - Always visible */}
      <div 
        className="flex items-center space-x-2 p-2 cursor-pointer hover:bg-secondary transition-colors duration-150"
        onClick={onToggleExpansion}
      >
        {/* Expand/Collapse Icon */}
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>

        {/* Agent Icon */}
        <div className="flex items-center flex-shrink-0">
          <span className="text-sm">{getAgentTypeIcon(log.agent_name)}</span>
        </div>

        {/* Main Content */}
        <div className="flex-grow min-w-0">
          <div className="flex items-center space-x-2 mb-1">
            <span className="font-medium text-foreground text-xs truncate">
              {log.agent_name}
            </span>
            <span className="text-xs text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
              {(() => {
                // console.log('Log entry timestamp:', {
                //   timestamp: log.timestamp,
                //   timestampType: typeof log.timestamp,
                //   isDate: log.timestamp instanceof Date,
                //   formatted: formatActivityLogTime(log.timestamp)
                // });
                return formatActivityLogTime(log.timestamp);
              })()}
            </span>
            {(() => {
              const parsedAction = ActionParser.parseAction(log.action, log.agent_name);
              return parsedAction.phase && (
                <span className={`text-xs px-2 py-1 rounded ${ActionParser.getPhaseColor(parsedAction.phase)}`}>
                  {parsedAction.phase?.replace('_', ' ') || parsedAction.phase}
                </span>
              );
            })()}
          </div>
          
          <p className="text-foreground text-xs font-medium truncate break-all">
            {log.action}
          </p>
          
          {log.input_summary && !isExpanded && (
            <div className="text-muted-foreground text-xs mt-1">
              {(() => {
                // Parse and beautify the input summary
                const summary = log.input_summary;
                
                // Check if it contains Args: with JSON-like content
                const argsMatch = summary.match(/Args:\s*(\{.*\})/);
                if (argsMatch) {
                  try {
                    const argsStr = argsMatch[1];
                    // Try to parse as JSON (handle Python dict format)
                    const cleanedArgs = argsStr
                      .replace(/'/g, '"')  // Replace single quotes with double quotes
                      .replace(/True/g, 'true')
                      .replace(/False/g, 'false')
                      .replace(/None/g, 'null');
                    
                    const args = JSON.parse(cleanedArgs);
                    
                    // Display key arguments in a user-friendly way, filtering out technical paths
                    const keyArgs = [];
                    if (args.query) {
                      keyArgs.push(`Query: "${args.query.length > 50 ? args.query.substring(0, 50) + '...' : args.query}"`);
                    }
                    if (args.n_results) {
                      keyArgs.push(`Results: ${args.n_results}`);
                    }
                    if (args.use_reranker !== undefined) {
                      keyArgs.push(`Reranker: ${args.use_reranker ? 'Yes' : 'No'}`);
                    }
                    if (args.original_filename) {
                      keyArgs.push(`File: ${args.original_filename}`);
                    }
                    // Skip technical arguments like filepath, allowed_base_path, feedback_callback
                    
                    if (keyArgs.length > 0) {
                      return (
                        <div className="truncate">
                          <span className="text-muted-foreground">Args: </span>
                          {keyArgs.join(' | ')}
                        </div>
                      );
                    }
                  } catch (e) {
                    // If parsing fails, fall back to original display but truncated
                  }
                }
                
                // Fallback to original summary, truncated
                return <div className="truncate break-all">{summary}</div>;
              })()}
            </div>
          )}
          
          {log.error_message && (
            <p className="text-destructive text-xs mt-1 font-medium">
              Error: {log.error_message}
            </p>
          )}
        </div>

        {/* Compact Model Details - Smaller and more beautified */}
        {log.model_details && (
          <div className="flex-shrink-0">
            <div className="flex items-center space-x-1">
              {log.model_details.cost !== undefined && log.model_details.cost !== null && (
                <div className="bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded-full text-xs font-medium">
                  ${log.model_details.cost.toFixed(4)}
                </div>
              )}
              {log.model_details.duration_sec && (
                <div className="bg-primary/10 text-primary px-1.5 py-0.5 rounded-full text-xs font-medium">
                  {log.model_details.duration_sec.toFixed(1)}s
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-border bg-secondary">
          <div className="p-3 overflow-hidden">
            <div className="max-w-full overflow-x-auto">
              {children}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
