import React from 'react';
import type { ExecutionLogEntry } from './AgentActivityLog';

interface ModelDetailsRendererProps {
  log: ExecutionLogEntry;
}

export const ModelDetailsRenderer: React.FC<ModelDetailsRendererProps> = ({ log }) => {
  if (!log.model_details) return null;

  return (
    <div className="mb-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-2">Model Performance</h4>
      <div className="bg-white border border-gray-200 rounded p-3">
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div>
            <div className="text-gray-600">Provider:</div>
            <div className="font-medium">{log.model_details.provider}</div>
          </div>
          <div>
            <div className="text-gray-600">Model:</div>
            <div className="font-medium font-mono">{log.model_details.model_name}</div>
          </div>
          <div>
            <div className="text-gray-600">Duration:</div>
            <div className="font-medium">{log.model_details.duration_sec?.toFixed(2)}s</div>
          </div>
          {log.model_details.cost !== undefined && log.model_details.cost !== null && (
            <div>
              <div className="text-gray-600">Cost:</div>
              <div className="font-medium">${log.model_details.cost.toFixed(4)}</div>
            </div>
          )}
          {log.model_details.total_tokens && (
            <div className="col-span-2">
              <div className="text-gray-600">Tokens:</div>
              <div className="font-medium">
                {log.model_details.prompt_tokens} + {log.model_details.completion_tokens} = {log.model_details.total_tokens}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
