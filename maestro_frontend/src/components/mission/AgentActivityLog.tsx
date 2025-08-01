import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent } from '../ui/card';
import { Bot, Activity } from 'lucide-react';
import { LogEntryCard } from './LogEntryCard.tsx';
import { ResearchAgentLog } from './ResearchAgentLog.tsx';
import { PlanningAgentLog } from './PlanningAgentLog.tsx';
import { WritingAgentLog } from './WritingAgentLog.tsx';
import { ReflectionAgentLog } from './ReflectionAgentLog.tsx';
import { DefaultLogRenderer } from './DefaultLogRenderer.tsx';

export interface ExecutionLogEntry {
  timestamp: Date;
  agent_name: string;
  action: string;
  input_summary?: string;
  output_summary?: string;
  status: 'success' | 'failure' | 'warning' | 'running';
  error_message?: string;
  full_input?: any;
  full_output?: any;
  // Database fields for cost and token tracking
  cost?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  native_tokens?: number;
  // Legacy model_details for backward compatibility
  model_details?: {
    provider?: string;
    model_name?: string;
    duration_sec?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    cost?: number;
  };
  tool_calls?: Array<{
    tool_name: string;
    arguments: any;
    result_summary: string;
    error?: string;
  }>;
  file_interactions?: string[];
}

interface AgentActivityLogProps {
  logs: ExecutionLogEntry[];
  isLoading?: boolean;
  missionStatus?: string;
}

export const AgentActivityLog: React.FC<AgentActivityLogProps> = ({ 
  logs, 
  isLoading = false, 
  missionStatus 
}) => {
  const [expandedLogs, setExpandedLogs] = useState<Set<number>>(new Set());
  const logContainerRef = useRef<HTMLDivElement>(null);

  const toggleLogExpansion = (index: number) => {
    setExpandedLogs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (logContainerRef.current) {
      // Use requestAnimationFrame to ensure DOM is updated before scrolling
      requestAnimationFrame(() => {
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      });
    }
  }, [logs]);

  const renderLogEntry = (log: ExecutionLogEntry, index: number) => {
    const isExpanded = expandedLogs.has(index);
    
    // Choose the appropriate renderer based on agent name
    let LogRenderer;
    const agentName = log.agent_name.toLowerCase();
    
    if (agentName.includes('research')) {
      LogRenderer = ResearchAgentLog;
    } else if (agentName.includes('planning')) {
      LogRenderer = PlanningAgentLog;
    } else if (agentName.includes('writing')) {
      LogRenderer = WritingAgentLog;
    } else if (agentName.includes('reflection')) {
      LogRenderer = ReflectionAgentLog;
    } else {
      LogRenderer = DefaultLogRenderer;
    }


    return (
      <LogEntryCard
        key={index}
        log={log}
        isExpanded={isExpanded}
        onToggleExpansion={() => toggleLogExpansion(index)}
      >
        <LogRenderer log={log} isExpanded={isExpanded} />
      </LogEntryCard>
    );
  };

  return (
    <div className="flex flex-col h-full max-h-full overflow-hidden space-y-2">
      <div className="flex items-center space-x-2 flex-shrink-0">
        <Bot className="h-4 w-4 text-primary" />
        <h3 className="text-base font-semibold text-foreground">Agent Activity Log</h3>
        {logs.length > 0 && (
          <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
            {logs.length} entries
          </span>
        )}
      </div>

      <Card className="flex-1 flex flex-col min-h-0">
        <CardContent ref={logContainerRef} className="p-0 space-y-2 overflow-y-auto flex-1 min-h-0">
          {isLoading && logs.length === 0 && (
            <div className="flex justify-center items-center h-full p-4">
              <div className="flex items-center space-x-2">
                <Activity className="h-4 w-4 text-primary animate-spin" />
                <p className="text-xs text-muted-foreground">Loading agent activity...</p>
              </div>
            </div>
          )}
          
          {!isLoading && logs.length === 0 && (
            <div className="flex flex-col justify-center items-center h-full text-center text-muted-foreground p-4">
              <Bot className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              <p className="text-sm font-medium mb-1">No Agent Activity Yet</p>
              <p className="text-xs">
                {missionStatus === 'running'
                  ? 'Waiting for the first agent to start working...'
                  : 'Start a research mission to see the live activity log.'}
              </p>
            </div>
          )}
          
          {logs.map((log, index) => renderLogEntry(log, index))}
        </CardContent>
      </Card>
    </div>
  );
};
