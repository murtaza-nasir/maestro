import React from 'react';
import { Clock, DollarSign, CheckCircle, XCircle, AlertCircle, Info, Cpu, Database } from 'lucide-react';
import type { ExecutionLogEntry } from './AgentActivityLog';
import { ActionParser } from './ActionParser';
import { ensureDate } from '../../utils/timezone';

interface SummaryRendererProps {
  log: ExecutionLogEntry;
}

export const SummaryRenderer: React.FC<SummaryRendererProps> = ({ log }) => {
  const parsedAction = ActionParser.parseAction(log.action, log.agent_name);
  const actionIcon = ActionParser.getActionIcon(parsedAction);
  const actionDescription = ActionParser.getActionDescription(parsedAction);
  const phaseColor = ActionParser.getPhaseColor(parsedAction.phase);

  const formatDuration = (duration: number) => {
    if (duration < 1) return `${(duration * 1000).toFixed(0)}ms`;
    return `${duration.toFixed(2)}s`;
  };

  const formatCost = (cost: number) => {
    return `$${cost.toFixed(6)}`;
  };

  const formatTokens = (tokens: number) => {
    if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`;
    return tokens.toString();
  };

  return (
    <div className="bg-gradient-to-r from-gray-50 to-gray-100 rounded-lg p-4 border border-gray-200">
      {/* Header Section */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center space-x-3">
          <span className="text-2xl">{actionIcon}</span>
          <div>
            <h3 className="font-semibold text-gray-900 text-lg">{log.agent_name}</h3>
            <p className="text-sm text-gray-600">{actionDescription}</p>
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-medium ${phaseColor} whitespace-nowrap`}>
          {parsedAction.phase || 'Unknown Phase'}
        </div>
      </div>

      {/* Timestamp and Status */}
      <div className="flex items-center justify-between mb-3 text-sm">
        <div className="flex items-center text-gray-600">
          <Clock className="h-4 w-4 mr-2" />
          <span>{ensureDate(log.timestamp).toLocaleTimeString()}</span>
        </div>
        
        <div className="flex items-center">
          {log.status === 'success' && <CheckCircle className="h-4 w-4 mr-2 text-green-500" />}
          {log.status === 'failure' && <XCircle className="h-4 w-4 mr-2 text-red-500" />}
          {log.status === 'warning' && <AlertCircle className="h-4 w-4 mr-2 text-yellow-500" />}
          <span className={`font-medium text-xs ${
            log.status === 'success' ? 'text-green-600' :
            log.status === 'failure' ? 'text-red-600' :
            log.status === 'warning' ? 'text-yellow-600' :
            'text-gray-600'
          }`}>
            {log.status.charAt(0).toUpperCase() + log.status.slice(1)}
          </span>
        </div>
      </div>

      {/* Performance Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        {log.model_details?.duration_sec && (
          <div className="bg-white rounded p-2 text-center">
            <div className="flex items-center justify-center text-gray-500 mb-1">
              <Clock className="h-3 w-3 mr-1" />
              <span className="text-xs">Time</span>
            </div>
            <div className="text-sm font-semibold text-gray-900">
              {formatDuration(log.model_details.duration_sec)}
            </div>
          </div>
        )}
        
        {log.model_details?.cost !== undefined && log.model_details?.cost !== null && (
          <div className="bg-white rounded p-2 text-center">
            <div className="flex items-center justify-center text-gray-500 mb-1">
              <DollarSign className="h-3 w-3 mr-1" />
              <span className="text-xs">Cost</span>
            </div>
            <div className="text-sm font-semibold text-green-600">
              {formatCost(log.model_details.cost)}
            </div>
          </div>
        )}
        
        {(log.model_details?.prompt_tokens || log.model_details?.completion_tokens) && (
          <div className="bg-white rounded p-2 text-center">
            <div className="flex items-center justify-center text-gray-500 mb-1">
              <Cpu className="h-3 w-3 mr-1" />
              <span className="text-xs">Tokens</span>
            </div>
            <div className="text-sm font-semibold text-blue-600">
              {log.model_details.prompt_tokens !== undefined && (
                <div>P: {formatTokens(log.model_details.prompt_tokens)}</div>
              )}
              {log.model_details.completion_tokens !== undefined && (
                <div>C: {formatTokens(log.model_details.completion_tokens)}</div>
              )}
            </div>
          </div>
        )}
        
        {log.model_details?.model_name && (
          <div className="bg-white rounded p-2 text-center">
            <div className="flex items-center justify-center text-gray-500 mb-1">
              <Database className="h-3 w-3 mr-1" />
              <span className="text-xs">Model</span>
            </div>
            <div className="text-xs font-semibold text-gray-900 truncate">
              {log.model_details.model_name.split('/').pop()}
            </div>
          </div>
        )}
      </div>

      {/* Input Summary */}
      {log.input_summary && (
        <div className="mb-3">
          <div className="flex items-center text-sm text-gray-600 mb-2">
            <Info className="h-4 w-4 mr-2" />
            <span className="font-medium">Input Context</span>
          </div>
          <div className="bg-white border border-gray-200 rounded p-3">
            <p className="text-sm text-gray-800">{log.input_summary}</p>
          </div>
        </div>
      )}

      {/* Output Summary */}
      {log.output_summary && (
        <div className="mb-3">
          <div className="flex items-center text-sm text-gray-600 mb-2">
            <Info className="h-4 w-4 mr-2" />
            <span className="font-medium">Output Summary</span>
          </div>
          <div className="bg-white border border-gray-200 rounded p-3">
            <p className="text-sm text-gray-800">{log.output_summary}</p>
          </div>
        </div>
      )}

      {/* Error Message */}
      {log.error_message && (
        <div className="mb-3">
          <div className="flex items-center text-sm text-red-600 mb-2">
            <XCircle className="h-4 w-4 mr-2" />
            <span className="font-medium">Error Details</span>
          </div>
          <div className="bg-red-50 border border-red-200 rounded p-3">
            <p className="text-sm text-red-800">{log.error_message}</p>
          </div>
        </div>
      )}
    </div>
  );
};
