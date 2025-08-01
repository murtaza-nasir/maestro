import React, { useMemo } from 'react';
import { DollarSign, Search, Clock, Zap } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';

interface MissionHeaderStatsProps {
  logs: ExecutionLogEntry[];
  missionStatus?: string;
}

export const MissionHeaderStats: React.FC<MissionHeaderStatsProps> = ({ 
  logs, 
  missionStatus 
}) => {
  const stats = useMemo(() => {
    // Calculate cost from both direct cost field (database logs) and model_details (legacy logs)
    const totalCost = logs.reduce((sum, log) => {
      const directCost = log.cost || 0;
      const modelDetailsCost = log.model_details?.cost || 0;
      return sum + Math.max(directCost, modelDetailsCost); // Use the higher value
    }, 0);
    
    // Calculate tokens from both direct token fields (database logs) and model_details (legacy logs)
    const totalTokens = logs.reduce((sum, log) => {
      const directTokens = (log.prompt_tokens || 0) + (log.completion_tokens || 0) + (log.native_tokens || 0);
      const modelDetailsTokens = log.model_details?.total_tokens || 0;
      return sum + Math.max(directTokens, modelDetailsTokens); // Use the higher value
    }, 0);
    
    const totalDuration = logs.reduce((sum, log) => 
      sum + (log.model_details?.duration_sec || 0), 0
    );
    
    // Count web searches from tool calls
    const webSearches = logs.reduce((sum, log) => {
      if (!log.tool_calls) return sum;
      return sum + log.tool_calls.filter(tool => 
        tool.tool_name && (
          tool.tool_name.toLowerCase().includes('search') || 
          tool.tool_name.toLowerCase().includes('web') ||
          tool.tool_name.toLowerCase().includes('tavily')
        )
      ).length;
    }, 0);
    
    return {
      totalCost,
      totalTokens,
      totalDuration,
      webSearches
    };
  }, [logs]);

  const formatCurrency = (amount: number) => `$${amount.toFixed(4)}`;
  const formatNumber = (num: number) => num.toLocaleString();
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  };

  // Only show stats if mission is running or has logs
  if (!logs.length && missionStatus !== 'running') {
    return null;
  }

  return (
    <div className="flex items-center space-x-2 text-xs">
      {/* Total Cost */}
      <div className="flex items-center space-x-1">
        <DollarSign className="h-3 w-3 text-green-600" />
        <span className="text-green-700 font-medium">
          {formatCurrency(stats.totalCost)}
        </span>
      </div>

      {/* Web Searches */}
      <div className="flex items-center space-x-1">
        <Search className="h-3 w-3 text-blue-600" />
        <span className="text-blue-700 font-medium">
          {stats.webSearches}
        </span>
      </div>

      {/* Duration (only show if mission has run) */}
      {stats.totalDuration > 0 && (
        <div className="flex items-center space-x-1">
          <Clock className="h-3 w-3 text-purple-600" />
          <span className="text-purple-700 font-medium">
            {formatDuration(stats.totalDuration)}
          </span>
        </div>
      )}

      {/* Tokens (only show if significant) */}
      {stats.totalTokens > 0 && (
        <div className="flex items-center space-x-1">
          <Zap className="h-3 w-3 text-orange-600" />
          <span className="text-orange-700 font-medium">
            {formatNumber(stats.totalTokens)}
          </span>
        </div>
      )}
    </div>
  );
};
