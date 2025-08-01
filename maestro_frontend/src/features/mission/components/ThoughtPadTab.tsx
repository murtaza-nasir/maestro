import React from 'react';
import { Brain, Lightbulb, Bot } from 'lucide-react';
import type { ThoughtEntry } from '../types';

interface ThoughtPadTabProps {
  thoughts: ThoughtEntry[];
}

export const ThoughtPadTab: React.FC<ThoughtPadTabProps> = ({ thoughts }) => {
  if (!thoughts || thoughts.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        <Brain className="h-8 w-8 mx-auto mb-2 text-gray-300" />
        <p className="text-sm">No thoughts have been recorded for this mission yet.</p>
        <p className="text-xs text-gray-400 mt-1">Agent insights and reasoning will appear here.</p>
      </div>
    );
  }

  const getAgentIcon = (agentName: string) => {
    const name = agentName.toLowerCase();
    if (name.includes('planning')) return '📋';
    if (name.includes('research')) return '🔍';
    if (name.includes('writing')) return '✍️';
    if (name.includes('reflection')) return '🤔';
    if (name.includes('controller')) return '⚙️';
    return '🤖';
  };

  const getAgentColor = (agentName: string) => {
    const name = agentName.toLowerCase();
    if (name.includes('planning')) return 'bg-purple-50 border-purple-200';
    if (name.includes('research')) return 'bg-blue-50 border-blue-200';
    if (name.includes('writing')) return 'bg-green-50 border-green-200';
    if (name.includes('reflection')) return 'bg-orange-50 border-orange-200';
    if (name.includes('controller')) return 'bg-gray-50 border-gray-200';
    return 'bg-indigo-50 border-indigo-200';
  };

  return (
    <div className="p-3 space-y-3">
      {thoughts.map((thought) => (
        <div key={thought.thought_id} className={`border rounded-lg overflow-hidden ${getAgentColor(thought.agent_name)}`}>
          {/* Main Content */}
          <div className="p-4">
            <div className="flex items-start space-x-3">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center text-sm border border-gray-200">
                  {getAgentIcon(thought.agent_name)}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center space-x-2 mb-2">
                  <Lightbulb className="h-4 w-4 text-yellow-500" />
                  <span className="text-xs font-medium text-gray-600">Thought</span>
                </div>
                <p className="text-sm text-gray-800 leading-relaxed">{thought.content}</p>
              </div>
            </div>
          </div>
          
          {/* Metadata Footer */}
          <div className="px-4 py-2 bg-white/50 border-t border-white/20">
            <div className="flex items-center space-x-2 text-xs">
              <Bot className="h-3 w-3 text-gray-500" />
              <span className="text-gray-500">by</span>
              <span className="font-medium text-gray-700">{thought.agent_name}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
