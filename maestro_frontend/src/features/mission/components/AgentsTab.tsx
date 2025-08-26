import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
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
  onLoadAllLogs?: () => void;
  isLoadingMoreLogs?: boolean;
  totalLogsCount?: number;
}

export const AgentsTab: React.FC<AgentsTabProps> = ({ 
  missionId,
  hasMoreLogs,
  onLoadMoreLogs,
  onLoadAllLogs,
  isLoadingMoreLogs,
  totalLogsCount
}) => {
  const { t } = useTranslation();
  const { activeMission, missionLogs } = useMissionStore();
  const [isLoading, setIsLoading] = useState(false);

  const logs = missionLogs[missionId] || [];
  
  useEffect(() => {
  }, [missionId, logs]);

  const memoizedLogs = useMemo(() => {
    return logs;
  }, [logs]);

  useEffect(() => {
    if (missionId && logs.length === 0) {
      setIsLoading(true);
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
            {t('agentsTab.activityLog')}
          </TabsTrigger>
          <TabsTrigger value="status">{t('agentsTab.agentStatus')}</TabsTrigger>
          <TabsTrigger value="stats">{t('agentsTab.statistics')}</TabsTrigger>
        </TabsList>
        
        <TabsContent value="activity" className="flex-1 mt-2 overflow-hidden">
          <AgentActivityLog 
            logs={memoizedLogs}
            isLoading={isLoading}
            missionStatus={activeMission?.status}
            missionId={missionId}
            hasMore={hasMoreLogs}
            onLoadMore={onLoadMoreLogs}
            onLoadAll={onLoadAllLogs}
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
