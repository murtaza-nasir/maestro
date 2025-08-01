import React from 'react';
import { Target, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import type { GoalEntry } from '../types';

interface GoalPadTabProps {
  goals: GoalEntry[];
}

export const GoalPadTab: React.FC<GoalPadTabProps> = ({ goals }) => {
  if (!goals || goals.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        <Target className="h-8 w-8 mx-auto mb-2 text-gray-300" />
        <p className="text-sm">No goals have been set for this mission yet.</p>
      </div>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'active':
        return <Clock className="h-4 w-4 text-blue-500" />;
      case 'pending':
        return <Clock className="h-4 w-4 text-yellow-500" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'bg-green-50 border-green-200';
      case 'active':
        return 'bg-blue-50 border-blue-200';
      case 'pending':
        return 'bg-yellow-50 border-yellow-200';
      default:
        return 'bg-gray-50 border-gray-200';
    }
  };

  return (
    <div className="p-3 space-y-3">
      {goals.map((goal) => (
        <div key={goal.goal_id} className={`border rounded-lg overflow-hidden ${getStatusColor(goal.status)}`}>
          {/* Main Content */}
          <div className="p-4">
            <div className="flex items-start space-x-3">
              <Target className="h-5 w-5 text-gray-600 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-gray-800 leading-relaxed flex-1">{goal.text}</p>
            </div>
          </div>
          
          {/* Metadata Footer */}
          <div className="px-4 py-2 bg-white/50 border-t border-white/20">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-2">
                {getStatusIcon(goal.status)}
                <span className="font-medium text-gray-700">
                  {goal.status.charAt(0).toUpperCase() + goal.status.slice(1)}
                </span>
              </div>
              {goal.source_agent && (
                <div className="flex items-center space-x-1 text-gray-500">
                  <span>by</span>
                  <span className="font-medium">{goal.source_agent}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
