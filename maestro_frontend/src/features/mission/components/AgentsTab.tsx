import React, { useState, useEffect, useMemo } from 'react';
import { useMissionStore } from '../store';
import { 
  AgentActivityLog, 
  MissionStatsDashboard, 
  AgentStatusIndicator,
} from '../../../components/mission';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';

interface AgentsTabProps {
  missionId: string;
  hasMoreLogs?: boolean;
  onLoadMoreLogs?: () => void;
  isLoadingMoreLogs?: boolean;
  totalLogsCount?: number;
}

export const AgentsTab: React.FC<AgentsTabProps> = ({ 
  missionId,
  hasMoreLogs,
  onLoadMoreLogs,
  isLoadingMoreLogs,
  totalLogsCount
}) => {
  const { activeMission, missionLogs } = useMissionStore();
  const [isLoading, setIsLoading] = useState(false);

  // Get logs from the store (shared with ResearchPanel)
  const logs = missionLogs[missionId] || [];
  
  // Debug logging to understand what's happening
  useEffect(() => {
    // console.log(`AgentsTab: missionId=${missionId}, logs.length=${logs.length}`);
    // console.log('AgentsTab: First few logs:', logs.slice(0, 3));
  }, [missionId, logs]);

  // Memoize logs to prevent unnecessary re-renders
  const memoizedLogs = useMemo(() => {
    // Keep only the most recent logs to prevent memory issues
    return logs;
  }, [logs]);

  // Set loading state when mission changes
  useEffect(() => {
    if (missionId && logs.length === 0) {
      setIsLoading(true);
      // Loading will be handled by ResearchPanel, just wait a bit
      const timer = setTimeout(() => setIsLoading(false), 1000);
      return () => clearTimeout(timer);
    } else {
      setIsLoading(false);
    }
  }, [missionId, logs.length]);

  return (
    <div className="h-full flex flex-col">
      <Tabs defaultValue="activity" className="h-full flex flex-col">
        <TabsList className="grid w-full grid-cols-3 bg-secondary">
          <TabsTrigger value="activity" className="flex items-center gap-2">
            Activity Log
          </TabsTrigger>
          <TabsTrigger value="status">Agent Status</TabsTrigger>
          <TabsTrigger value="stats">Statistics</TabsTrigger>
        </TabsList>
        
        <TabsContent value="activity" className="flex-1 mt-2 overflow-hidden">
          <AgentActivityLog 
            logs={memoizedLogs}
            isLoading={isLoading}
            missionStatus={activeMission?.status}
            missionId={missionId}
            hasMore={hasMoreLogs}
            onLoadMore={onLoadMoreLogs}
            isLoadingMore={isLoadingMoreLogs}
            totalLogs={totalLogsCount}
          />
        </TabsContent>
        
        <TabsContent value="status" className="flex-1 mt-2 overflow-hidden">
          <div className="h-full overflow-auto">
            <AgentStatusIndicator 
              logs={memoizedLogs}
              missionStatus={activeMission?.status}
            />
          </div>
        </TabsContent>
        
        <TabsContent value="stats" className="flex-1 mt-2 overflow-hidden">
          <div className="overflow-auto">
            <MissionStatsDashboard 
              logs={memoizedLogs}
              missionStatus={activeMission?.status}
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};
