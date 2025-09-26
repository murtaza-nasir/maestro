import React, { useEffect, useState } from 'react';
import { Activity, Loader2, PlayCircle, PauseCircle, CheckCircle } from 'lucide-react';
import { Card } from '../ui/card';

interface PhaseDetails {
  phase?: string;
  round?: number;
  total_rounds?: number;
  section?: string;
  section_id?: string;
  cycle?: number;
  max_cycles?: number;
  step?: string;
  progress?: number;
}

interface PhaseStatus {
  mission_id: string;
  status: string;
  execution_phase: string;
  completed_phases: string[];
  current_phase: string;
  phase_details: PhaseDetails;
  notes_count: number;
  has_plan: boolean;
}

interface PhaseStatusIndicatorProps {
  missionId: string;
}

export const PhaseStatusIndicator: React.FC<PhaseStatusIndicatorProps> = ({ missionId }) => {
  const [phaseStatus, setPhaseStatus] = useState<PhaseStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fetchPhaseStatus = async () => {
      if (!missionId) return;
      
      setIsLoading(true);
      try {
        const response = await fetch(`/api/missions/${missionId}/phase-status`, {
          credentials: 'include',
        });
        
        if (response.ok) {
          const data = await response.json();
          setPhaseStatus(data);
        }
      } catch (error) {
        console.error('Failed to fetch phase status:', error);
      } finally {
        setIsLoading(false);
      }
    };

    // Initial fetch
    fetchPhaseStatus();
    
    // Polling interval for updates
    const interval = setInterval(fetchPhaseStatus, 3000); // Update every 3 seconds
    
    return () => clearInterval(interval);
  }, [missionId]);

  if (isLoading && !phaseStatus) {
    return (
      <Card className="bg-secondary/50 border-muted/50 p-2">
        <div className="flex items-center space-x-2 text-xs">
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Loading phase information...</span>
        </div>
      </Card>
    );
  }

  if (!phaseStatus) {
    return null;
  }

  const { phase_details } = phaseStatus;
  
  // Get status icon and color scheme
  const getStatusIcon = () => {
    if (phaseStatus.status === 'completed') return <CheckCircle className="h-3 w-3" />;
    if (phaseStatus.status === 'paused') return <PauseCircle className="h-3 w-3" />;
    if (phaseStatus.status === 'running') return <PlayCircle className="h-3 w-3" />;
    return <Activity className="h-3 w-3" />;
  };

  const getStatusColor = () => {
    if (phaseStatus.status === 'completed') return 'text-green-500 dark:text-green-400';
    if (phaseStatus.status === 'failed') return 'text-red-500 dark:text-red-400';
    if (phaseStatus.status === 'paused') return 'text-yellow-500 dark:text-yellow-400';
    return 'text-blue-500 dark:text-blue-400';
  };

  const getProgressBarColor = () => {
    if (phaseStatus.status === 'completed') return 'bg-green-500 dark:bg-green-400';
    if (phaseStatus.status === 'failed') return 'bg-red-500 dark:bg-red-400';
    if (phaseStatus.status === 'paused') return 'bg-yellow-500 dark:bg-yellow-400';
    return 'bg-blue-500 dark:bg-blue-400';
  };

  // Build phase display components
  const phaseInfo = [];
  
  if (phase_details.phase) {
    phaseInfo.push(
      <span key="phase" className="font-medium">
        {phase_details.phase}
      </span>
    );
  }
  
  if (phase_details.round && phase_details.total_rounds) {
    phaseInfo.push(
      <span key="round" className="text-muted-foreground">
        Round {phase_details.round}/{phase_details.total_rounds}
      </span>
    );
  }
  
  if (phase_details.section) {
    phaseInfo.push(
      <span key="section" className="text-primary/80">
        {phase_details.section}
      </span>
    );
    
    if (phase_details.cycle && phase_details.max_cycles) {
      phaseInfo.push(
        <span key="cycle" className="text-muted-foreground">
          Cycle {phase_details.cycle}/{phase_details.max_cycles}
        </span>
      );
    }
  } else if (phase_details.step) {
    phaseInfo.push(
      <span key="step" className="text-muted-foreground italic">
        {phase_details.step}
      </span>
    );
  }

  return (
    <Card className="bg-secondary/30 border-muted/50 p-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className={`flex items-center space-x-1.5 ${getStatusColor()}`}>
            {getStatusIcon()}
            <span className="text-xs font-medium uppercase tracking-wider">
              {phaseStatus.status === 'running' ? 'Processing' : phaseStatus.status}
            </span>
          </div>
          
          <div className="flex items-center space-x-2 text-xs">
            {phaseInfo.map((item, index) => (
              <React.Fragment key={index}>
                {index > 0 && <span className="text-muted-foreground">•</span>}
                {item}
              </React.Fragment>
            ))}
          </div>
        </div>
        
        {phase_details.progress !== undefined && (
          <div className="flex items-center space-x-2">
            <div className="w-32 h-1.5 bg-secondary rounded-full overflow-hidden">
              <div 
                className={`h-full ${getProgressBarColor()} transition-all duration-300`}
                style={{ width: `${Math.min(100, Math.max(0, phase_details.progress))}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground font-mono">
              {Math.round(phase_details.progress || 0)}%
            </span>
          </div>
        )}
      </div>
    </Card>
  );
};