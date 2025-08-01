import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { 
  DollarSign, 
  Clock, 
  Zap, 
  FileText, 
  Users, 
  TrendingUp,
  Activity,
  Target
} from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ActionParser } from './ActionParser';

interface MissionStatsDashboardProps {
  logs: ExecutionLogEntry[];
  missionStatus?: string;
}

export const MissionStatsDashboard: React.FC<MissionStatsDashboardProps> = ({ 
  logs, 
  // missionStatus 
}) => {
  const stats = useMemo(() => {
    const totalCost = logs.reduce((sum, log) => 
      sum + (log.model_details?.cost || 0), 0
    );
    
    const totalTokens = logs.reduce((sum, log) => 
      sum + (log.model_details?.total_tokens || 0), 0
    );
    
    const totalDuration = logs.reduce((sum, log) => 
      sum + (log.model_details?.duration_sec || 0), 0
    );
    
    const toolCalls = logs.reduce((sum, log) => 
      sum + (log.tool_calls?.length || 0), 0
    );
    
    const fileInteractions = logs.reduce((sum, log) => 
      sum + (log.file_interactions?.length || 0), 0
    );
    
    const agentActivity = logs.reduce((acc, log) => {
      const agentName = log.agent_name;
      if (!acc[agentName]) {
        acc[agentName] = { count: 0, cost: 0, tokens: 0 };
      }
      acc[agentName].count++;
      acc[agentName].cost += log.model_details?.cost || 0;
      acc[agentName].tokens += log.model_details?.total_tokens || 0;
      return acc;
    }, {} as Record<string, { count: number; cost: number; tokens: number }>);
    
    const phaseBreakdown = (() => {
      const acc: Record<string, number> = {};
      let currentPhase: string = 'initial_research'; // Default to initial_research

      logs.forEach(log => {
        const parsed = ActionParser.parseAction(log.action, log.agent_name);

        // If an action has a specific phase, it sets the new current phase.
        if (parsed.phase) {
          currentPhase = parsed.phase;
        }

        // An action without a phase (like a tool call) inherits the current phase.
        const phaseToLog = parsed.phase || currentPhase;

        if (!acc[phaseToLog]) {
          acc[phaseToLog] = 0;
        }
        acc[phaseToLog]++;
      });
      return acc;
    })();
    
    const successRate = logs.length > 0 
      ? (logs.filter(log => log.status === 'success').length / logs.length) * 100 
      : 0;
    
    return {
      totalCost,
      totalTokens,
      totalDuration,
      toolCalls,
      fileInteractions,
      agentActivity,
      phaseBreakdown,
      successRate,
      totalActions: logs.length
    };
  }, [logs]);

  const formatCurrency = (amount: number) => `$${amount.toFixed(4)}`;
  const formatNumber = (num: number) => num.toLocaleString();
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  };

  return (
    <div className="h-full flex flex-col space-y-2 text-xs">
      {/* Overview Cards - More compact grid */}
      <div className="grid grid-cols-4 gap-2">
        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <DollarSign className="h-3 w-3 text-green-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">Total Cost</p>
              <p className="text-sm font-bold text-green-600 leading-tight">
                {formatCurrency(stats.totalCost)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <Zap className="h-3 w-3 text-blue-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">Total Tokens</p>
              <p className="text-sm font-bold text-blue-600 leading-tight">
                {formatNumber(stats.totalTokens)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <Clock className="h-3 w-3 text-purple-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">Duration</p>
              <p className="text-sm font-bold text-purple-600 leading-tight">
                {formatDuration(stats.totalDuration)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <Target className="h-3 w-3 text-orange-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">Success Rate</p>
              <p className="text-sm font-bold text-orange-600 leading-tight">
                {stats.successRate.toFixed(1)}%
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Agent Activity Breakdown - More compact */}
      <Card className="flex-1 min-h-0">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs flex items-center">
            <Users className="h-3 w-3 mr-1" />
            Agent Activity
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 overflow-auto">
          <div className="space-y-1">
            {Object.entries(stats.agentActivity).map(([agentName, activity]) => (
              <div key={agentName} className="flex items-center justify-between py-1">
                <div className="flex items-center space-x-1 min-w-0 flex-1">
                  <span className="text-xs font-medium truncate">{agentName}</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-1 py-0.5 rounded flex-shrink-0">
                    {activity.count}
                  </span>
                </div>
                <div className="text-right flex-shrink-0 ml-2">
                  <div className="text-xs font-medium">
                    {formatCurrency(activity.cost)}
                  </div>
                  <div className="text-xs text-gray-500">
                    {formatNumber(activity.tokens)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Phase Breakdown - More compact */}
      <Card className="flex-1 min-h-0">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs flex items-center">
            <TrendingUp className="h-3 w-3 mr-1" />
            Research Phases
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 overflow-auto">
          <div className="space-y-1">
            {Object.entries(stats.phaseBreakdown).map(([phase, count]) => {
              const percentage = stats.totalActions > 0 
                ? (count / stats.totalActions) * 100 
                : 0;
              
              const phaseLabels: Record<string, string> = {
                'initial_research': 'Initial Research',
                'structured_research': 'Structured Research',
                'writing': 'Writing',
                'reflection': 'Reflection',
                'orchestration': 'Orchestration',
                'unknown': 'Other'
              };
              
              const phaseColors: Record<string, string> = {
                'initial_research': 'bg-blue-500',
                'structured_research': 'bg-purple-500',
                'writing': 'bg-green-500',
                'reflection': 'bg-orange-500',
                'orchestration': 'bg-yellow-500',
                'unknown': 'bg-gray-500'
              };
              
              return (
                <div key={phase} className="py-1">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="truncate">{phaseLabels[phase] || phase}</span>
                    <span className="text-gray-500 flex-shrink-0 ml-2">{count} ({percentage.toFixed(1)}%)</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-1">
                    <div 
                      className={`h-1 rounded-full ${phaseColors[phase] || 'bg-gray-500'}`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Tool Usage - More compact */}
      <div className="grid grid-cols-2 gap-2 flex-shrink-0">
        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <Activity className="h-3 w-3 text-indigo-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">Tool Calls</p>
              <p className="text-sm font-bold text-indigo-600 leading-tight">
                {formatNumber(stats.toolCalls)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-0">
          <CardContent className="p-2">
            <div className="flex flex-col items-center text-center">
              <FileText className="h-3 w-3 text-teal-600 mb-1" />
              <p className="text-xs text-gray-600 leading-tight">File Interactions</p>
              <p className="text-sm font-bold text-teal-600 leading-tight">
                {formatNumber(stats.fileInteractions)}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
