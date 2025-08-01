import React, { useState, useEffect } from 'react'
import { Card } from './card'
import { Button } from './button'
import { getStorageUsage, clearOldStorageData } from '../../utils/storageUtils'

interface StorageUsageInfo {
  totalSize: number
  usage: Record<string, number>
  totalSizeMB: string
  strategies: Array<{
    name: string
    available: boolean
    maxSize: number
    persistent: boolean
  }>
}

export const StorageMonitor: React.FC = () => {
  const [storageInfo, setStorageInfo] = useState<StorageUsageInfo | null>(null)
  const [isClearing, setIsClearing] = useState(false)
  const [lastCleared, setLastCleared] = useState<Date | null>(null)

  const refreshStorageInfo = () => {
    const info = getStorageUsage()
    setStorageInfo(info)
  }

  useEffect(() => {
    refreshStorageInfo()
    
    // Refresh every 10 seconds
    const interval = setInterval(refreshStorageInfo, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleClearStorage = async () => {
    setIsClearing(true)
    try {
      clearOldStorageData()
      setLastCleared(new Date())
      
      // Wait a moment for cleanup to complete
      setTimeout(() => {
        refreshStorageInfo()
        setIsClearing(false)
      }, 1000)
    } catch (error) {
      console.error('Failed to clear storage:', error)
      setIsClearing(false)
    }
  }

  const handleMigrateToIndexedDB = async () => {
    setIsClearing(true)
    try {
      // Force migration by triggering a quota exceeded scenario
      const missionData = localStorage.getItem('mission-storage')
      if (missionData) {
        // Remove from localStorage to trigger migration
        localStorage.removeItem('mission-storage')
        console.log('Mission data removed from localStorage, will be migrated to IndexedDB on next save')
      }
      
      setLastCleared(new Date())
      setTimeout(() => {
        refreshStorageInfo()
        setIsClearing(false)
      }, 1000)
    } catch (error) {
      console.error('Failed to migrate storage:', error)
      setIsClearing(false)
    }
  }

  if (!storageInfo) {
    return (
      <Card className="p-4">
        <div className="text-sm text-gray-500">Loading storage information...</div>
      </Card>
    )
  }

  const getStorageColor = (sizeBytes: number) => {
    const sizeMB = sizeBytes / (1024 * 1024)
    if (sizeMB > 8) return 'text-red-600'
    if (sizeMB > 5) return 'text-yellow-600'
    return 'text-green-600'
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const sortedUsage = Object.entries(storageInfo.usage)
    .sort(([,a], [,b]) => b - a)
    .slice(0, 10) // Show top 10 largest items

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Storage Monitor</h3>
        <Button 
          onClick={refreshStorageInfo}
          variant="outline"
          size="sm"
        >
          Refresh
        </Button>
      </div>

      {/* Overall Usage */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium">Total localStorage Usage:</span>
          <span className={`text-sm font-mono ${getStorageColor(storageInfo.totalSize)}`}>
            {storageInfo.totalSizeMB} MB
          </span>
        </div>
        
        {/* Progress bar */}
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div 
            className={`h-2 rounded-full transition-all duration-300 ${
              parseFloat(storageInfo.totalSizeMB) > 8 ? 'bg-red-500' :
              parseFloat(storageInfo.totalSizeMB) > 5 ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            style={{ 
              width: `${Math.min(100, (parseFloat(storageInfo.totalSizeMB) / 10) * 100)}%` 
            }}
          />
        </div>
        <div className="text-xs text-gray-500">
          Recommended maximum: ~10 MB
        </div>
      </div>

      {/* Storage Breakdown */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium">Storage Breakdown:</h4>
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {sortedUsage.map(([key, size]) => (
            <div key={key} className="flex justify-between items-center text-sm">
              <span className="truncate flex-1 mr-2">{key}</span>
              <span className="font-mono text-xs">{formatBytes(size)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Available Storage Strategies */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium">Available Storage Options:</h4>
        <div className="space-y-1">
          {storageInfo.strategies.map((strategy) => (
            <div key={strategy.name} className="flex justify-between items-center text-sm">
              <span className="capitalize">{strategy.name.replace('db', 'DB')}</span>
              <div className="flex items-center space-x-2">
                <span className="text-xs text-gray-500">
                  {formatBytes(strategy.maxSize)} max
                </span>
                <span className={`text-xs px-2 py-1 rounded ${
                  strategy.available ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {strategy.available ? 'Available' : 'Unavailable'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="space-y-2 pt-2 border-t">
        <div className="flex space-x-2">
          <Button 
            onClick={handleClearStorage}
            disabled={isClearing}
            variant="outline"
            size="sm"
            className="flex-1"
          >
            {isClearing ? 'Clearing...' : 'Clear Old Data'}
          </Button>
          
          {storageInfo.strategies.find(s => s.name === 'indexeddb')?.available && (
            <Button 
              onClick={handleMigrateToIndexedDB}
              disabled={isClearing}
              variant="outline"
              size="sm"
              className="flex-1"
            >
              {isClearing ? 'Migrating...' : 'Use IndexedDB'}
            </Button>
          )}
        </div>
        
        {lastCleared && (
          <div className="text-xs text-gray-500 text-center">
            Last cleared: {lastCleared.toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* Warnings */}
      {parseFloat(storageInfo.totalSizeMB) > 8 && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md">
          <div className="text-sm text-red-800">
            <strong>Storage Warning:</strong> Your localStorage usage is very high. 
            Consider clearing old data or migrating to IndexedDB for better performance.
          </div>
        </div>
      )}
      
      {parseFloat(storageInfo.totalSizeMB) > 5 && parseFloat(storageInfo.totalSizeMB) <= 8 && (
        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
          <div className="text-sm text-yellow-800">
            <strong>Storage Notice:</strong> Your localStorage usage is getting high. 
            The system will automatically migrate large data to IndexedDB when needed.
          </div>
        </div>
      )}
    </Card>
  )
}
