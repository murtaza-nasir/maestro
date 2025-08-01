import React from 'react';
import { FileText, Bot } from 'lucide-react';

interface ScratchpadTabProps {
  scratchpad: string | null;
}

export const ScratchpadTab: React.FC<ScratchpadTabProps> = ({ scratchpad }) => {
  if (!scratchpad) {
    return (
      <div className="p-4 text-center text-gray-500">
        <FileText className="h-8 w-8 mx-auto mb-2 text-gray-300" />
        <p className="text-sm">The agent's scratchpad is empty.</p>
        <p className="text-xs text-gray-400 mt-1">Working notes and temporary thoughts will appear here.</p>
      </div>
    );
  }

  return (
    <div className="p-3">
      <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
        {/* Header */}
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center space-x-2">
            <Bot className="h-4 w-4 text-gray-600" />
            <span className="text-sm font-medium text-gray-700">Agent Working Notes</span>
          </div>
        </div>
        
        {/* Content */}
        <div className="p-4">
          <pre className="whitespace-pre-wrap text-sm text-gray-800 leading-relaxed font-mono">
            {scratchpad}
          </pre>
        </div>
        
        {/* Footer */}
        <div className="px-4 py-2 bg-gray-50 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            This scratchpad contains the agent's internal working notes and temporary thoughts during mission execution.
          </p>
        </div>
      </div>
    </div>
  );
};
