import React, { useEffect, useState } from 'react';
import { Activity, ChevronRight } from 'lucide-react';

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
      <div className="flex items-center space-x-1 text-xs text-muted-foreground">
        <Activity className="h-3 w-3 animate-spin" />
        <span>Loading phase...</span>
      </div>
    );
  }

  if (!phaseStatus) {
    return null;
  }

  const { phase_details } = phaseStatus;
  
  // Build the phase display string
  let phaseDisplay = phase_details.phase || phaseStatus.execution_phase || 'Unknown';
  
  // Add round information if available
  if (phase_details.round && phase_details.total_rounds) {
    phaseDisplay = `${phaseDisplay} (Round ${phase_details.round}/${phase_details.total_rounds})`;
  }
  
  // Add section and cycle information if available
  if (phase_details.section) {
    if (phase_details.cycle && phase_details.max_cycles) {
      phaseDisplay = `${phaseDisplay} - ${phase_details.section} (Cycle ${phase_details.cycle}/${phase_details.max_cycles})`;
    } else {
      phaseDisplay = `${phaseDisplay} - ${phase_details.section}`;
    }
  } else if (phase_details.step) {
    phaseDisplay = `${phaseDisplay} - ${phase_details.step}`;
  }

  // Get progress color based on status
  const getProgressColor = () => {
    if (phaseStatus.status === 'completed') return 'text-green-500';
    if (phaseStatus.status === 'failed') return 'text-red-500';
    if (phaseStatus.status === 'paused') return 'text-yellow-500';
    return 'text-blue-500';
  };

  return (
    <div className="flex items-center space-x-2 text-xs">
      <ChevronRight className="h-3 w-3 text-muted-foreground" />
      <div className="flex items-center space-x-2">
        <span className="text-muted-foreground">Phase:</span>
        <span className={`font-medium ${getProgressColor()}`}>
          {phaseDisplay}
        </span>
        {phase_details.progress !== undefined && (
          <div className="flex items-center space-x-1">
            <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
              <div 
                className={`h-full ${getProgressColor()} bg-current transition-all duration-300`}
                style={{ width: `${Math.min(100, Math.max(0, phase_details.progress))}%` }}
              />
            </div>
            <span className="text-muted-foreground">
              {Math.round(phase_details.progress || 0)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
};