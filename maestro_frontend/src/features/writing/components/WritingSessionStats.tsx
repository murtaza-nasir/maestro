import React, { useState, useEffect, useCallback } from 'react';
import { DollarSign, Search, FileText, Zap, RotateCcw, Trash2 } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { apiClient } from '../../../config/api';
import { writingWebSocketService, type WritingUpdate } from '../services/writingWebSocketService';

export interface WritingSessionStatsData {
  session_id: string;
  total_cost: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_native_tokens: number;
  total_web_searches: number;
  total_document_searches: number;
  created_at: string;
  updated_at: string;
}

interface WritingSessionStatsProps {
  sessionId: string;
  className?: string;
}

export const WritingSessionStats: React.FC<WritingSessionStatsProps> = ({ 
  sessionId, 
  className = '' 
}) => {
  const [stats, setStats] = useState<WritingSessionStatsData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch stats from API
  const fetchStats = useCallback(async () => {
    if (!sessionId) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await apiClient.get(`/api/writing/sessions/${sessionId}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch writing session stats:', error);
      setError('Failed to load stats');
      // Initialize with zero stats if fetch fails
      setStats({
        session_id: sessionId,
        total_cost: 0,
        total_prompt_tokens: 0,
        total_completion_tokens: 0,
        total_native_tokens: 0,
        total_web_searches: 0,
        total_document_searches: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  // Clear stats
  const clearStats = useCallback(async () => {
    if (!sessionId || isClearing) return;
    
    setIsClearing(true);
    setError(null);
    
    try {
      await apiClient.post(`/api/writing/sessions/${sessionId}/stats/clear`);
      // Reset stats to zero
      setStats(prev => prev ? {
        ...prev,
        total_cost: 0,
        total_prompt_tokens: 0,
        total_completion_tokens: 0,
        total_native_tokens: 0,
        total_web_searches: 0,
        total_document_searches: 0,
        updated_at: new Date().toISOString()
      } : null);
    } catch (error) {
      console.error('Failed to clear writing session stats:', error);
      setError('Failed to clear stats');
    } finally {
      setIsClearing(false);
    }
  }, [sessionId, isClearing]);

  // Handle WebSocket stats updates
  const handleStatsUpdate = useCallback((update: WritingUpdate) => {
    if (update.type === 'stats_update' && update.session_id === sessionId && update.data) {
      console.log('Received stats update via WebSocket:', update.data);
      setStats(prev => prev ? { ...prev, ...update.data } : update.data);
    }
  }, [sessionId]);

  // Set up WebSocket listener for real-time updates
  useEffect(() => {
    if (!sessionId) return;

    const unsubscribe = writingWebSocketService.onStatusUpdate(handleStatsUpdate);
    return unsubscribe;
  }, [sessionId, handleStatsUpdate]);

  // Fetch initial stats when session changes
  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // Format currency
  const formatCurrency = (amount: number) => `$${amount.toFixed(4)}`;
  
  // Format number with commas
  const formatNumber = (num: number) => num.toLocaleString();

  // Calculate total tokens
  const totalTokens = stats ? stats.total_prompt_tokens + stats.total_completion_tokens + stats.total_native_tokens : 0;

  if (!stats && !isLoading) {
    return null;
  }

  return (
    <div className={`flex items-center justify-between p-2 bg-stats-background rounded-md border border-border ${className}`}>
      <div className="flex items-center space-x-3 text-xs">
        {/* Total Cost */}
        <div className="flex items-center space-x-0.5">
          <DollarSign className="h-2.5 w-2.5 text-green-500" />
          <span className="text-green-500 font-medium text-xs">
            {isLoading ? '...' : formatCurrency(stats?.total_cost || 0)}
          </span>
        </div>

        {/* Total Tokens */}
        <div className="flex items-center space-x-0.5">
          <Zap className="h-2.5 w-2.5 text-orange-500" />
          <span className="text-orange-500 font-medium text-xs">
            {isLoading ? '...' : formatNumber(totalTokens)}
          </span>
          <span className="text-text-tertiary text-xs">tokens</span>
        </div>

        {/* Token Breakdown (show on hover or always visible) */}
        <div className="flex items-center space-x-1.5 text-text-secondary">
          <span className="text-xs">
            P: {isLoading ? '...' : formatNumber(stats?.total_prompt_tokens || 0)}
          </span>
          <span className="text-xs">
            C: {isLoading ? '...' : formatNumber(stats?.total_completion_tokens || 0)}
          </span>
          {stats && stats.total_native_tokens > 0 && (
            <span className="text-xs">
              N: {formatNumber(stats.total_native_tokens)}
            </span>
          )}
        </div>

        {/* Web Searches */}
        <div className="flex items-center space-x-0.5">
          <Search className="h-2.5 w-2.5 text-blue-500" />
          <span className="text-blue-500 font-medium text-xs">
            {isLoading ? '...' : stats?.total_web_searches || 0}
          </span>
          <span className="text-text-tertiary text-xs">web</span>
        </div>

        {/* Document Searches */}
        <div className="flex items-center space-x-0.5">
          <FileText className="h-2.5 w-2.5 text-purple-500" />
          <span className="text-purple-500 font-medium text-xs">
            {isLoading ? '...' : stats?.total_document_searches || 0}
          </span>
          <span className="text-text-tertiary text-xs">docs</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center space-x-1">
        {error && (
          <span className="text-xs text-destructive mr-2">
            {error}
          </span>
        )}
        
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchStats}
          disabled={isLoading}
          className="h-5 w-5 p-0 text-text-secondary hover:text-text-primary hover:bg-muted rounded"
          title="Refresh stats"
        >
          <RotateCcw className={`h-2.5 w-2.5 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={clearStats}
          disabled={isClearing || !stats || (stats.total_cost === 0 && totalTokens === 0 && stats.total_web_searches === 0 && stats.total_document_searches === 0)}
          className="h-5 w-5 p-0 text-text-secondary hover:text-destructive hover:bg-destructive/10 rounded"
          title="Clear stats"
        >
          <Trash2 className={`h-2.5 w-2.5 ${isClearing ? 'animate-pulse' : ''}`} />
        </Button>
      </div>
    </div>
  );
};
