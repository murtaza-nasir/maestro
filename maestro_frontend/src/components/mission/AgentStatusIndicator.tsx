import React, { useMemo } from 'react';
import { Activity, CheckCircle, AlertCircle, Clock, Pause } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { formatActivityLogTime } from '../../utils/timezone';

interface AgentStatusIndicatorProps {
  logs: ExecutionLogEntry[];
  missionStatus?: string;
}

interface AgentStatus {
  name: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  lastAction?: string;
  lastUpdate?: Date;
  actionCount: number;
}

export const AgentStatusIndicator: React.FC<AgentStatusIndicatorProps> = ({ 
  logs, 
  missionStatus 
}) => {
  const agentStatuses = useMemo(() => {
    const agentMap = new Map<string, AgentStatus>();
    
    // Initialize known agents
    const knownAgents = ['PlanningAgent', 'ResearchAgent', 'WritingAgent', 'ReflectionAgent', 'AgentController'];
    knownAgents.forEach(agent => {
      agentMap.set(agent, {
        name: agent,
        status: 'idle',
        actionCount: 0
      });
    });

    // Process logs to determine current status
    logs.forEach(log => {
      const agent = agentMap.get(log.agent_name) || {
        name: log.agent_name,
        status: 'idle' as const,
        actionCount: 0
      };

      agent.actionCount++;
      agent.lastAction = log.action;
      agent.lastUpdate = log.timestamp;

      // Determine status based on log status and mission status
      if (log.status === 'running' && missionStatus === 'running') {
        agent.status = 'running';
      } else if (log.status === 'failure') {
        agent.status = 'error';
      } else if (log.status === 'success') {
        agent.status = 'completed';
      }

      agentMap.set(log.agent_name, agent);
    });

    return Array.from(agentMap.values()).sort((a, b) => {
      // Sort by action count (most active first), then by name
      if (a.actionCount !== b.actionCount) {
        return b.actionCount - a.actionCount;
      }
      return a.name.localeCompare(b.name);
    });
  }, [logs, missionStatus]);

  const getStatusIcon = (status: AgentStatus['status']) => {
    switch (status) {
      case 'running':
        return <Activity className="h-4 w-4 text-primary animate-pulse" />;
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'error':
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      case 'idle':
        return <Pause className="h-4 w-4 text-muted-foreground" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusColor = (status: AgentStatus['status']) => {
    switch (status) {
      case 'running':
        return 'text-primary bg-primary/10';
      case 'completed':
        return 'text-green-500 bg-green-500/10';
      case 'error':
        return 'text-destructive bg-destructive/10';
      case 'idle':
        return 'text-muted-foreground bg-secondary';
      default:
        return 'text-muted-foreground bg-secondary';
    }
  };

  const getAgentIcon = (agentName: string) => {
    const name = agentName.toLowerCase();
    if (name.includes('planning')) return '📋';
    if (name.includes('research')) return '🔍';
    if (name.includes('writing')) return '✍️';
    if (name.includes('reflection')) return '🤔';
    if (name.includes('controller')) return '⚙️';
    return '🤖';
  };

  const formatTimestamp = (timestamp?: Date) => {
    if (!timestamp) return 'Never';
    try {
      return formatActivityLogTime(timestamp);
    } catch {
      return 'Invalid';
    }
  };

  const getStatusText = (status: AgentStatus['status']) => {
    switch (status) {
      case 'running':
        return 'Active';
      case 'completed':
        return 'Completed';
      case 'error':
        return 'Error';
      case 'idle':
        return 'Idle';
      default:
        return 'Unknown';
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">Agent Status</h3>
        <div className="text-sm text-muted-foreground">
          {agentStatuses.filter(a => a.status === 'running').length} active
        </div>
      </div>

      <div className="space-y-2">
        {agentStatuses.map(agent => (
          <div 
            key={agent.name}
            className={`relative ${getStatusColor(agent.status)} border border-border rounded-lg p-2 transition-all duration-200 overflow-hidden`}
          >
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-current opacity-75"></div>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="text-sm">{getAgentIcon(agent.name)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-medium text-foreground text-xs">{agent.name}</span>
                    <div className="flex items-center space-x-1">
                      {getStatusIcon(agent.status)}
                      <span className="text-xs text-muted-foreground">{getStatusText(agent.status)}</span>
                    </div>
                  </div>
                  {agent.lastAction && (
                    <div className="text-xs text-muted-foreground mt-1 truncate">
                      {agent.lastAction}
                    </div>
                  )}
                </div>
              </div>
              
              <div className="text-right flex-shrink-0 ml-2">
                <div className="text-xs font-medium text-foreground">
                  {agent.actionCount} actions
                </div>
                {agent.lastUpdate && (
                  <div className="text-xs text-muted-foreground">
                    {formatTimestamp(agent.lastUpdate)}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {agentStatuses.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <Activity className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
          <p>No agent activity yet</p>
        </div>
      )}
    </div>
  );
};
