// Enhanced storage utilities for handling large amounts of data efficiently

interface StorageStrategy {
  name: string;
  available: boolean;
  maxSize: number;
  persistent: boolean;
}

// Check available storage options
const getAvailableStorageStrategies = (): StorageStrategy[] => {
  const strategies: StorageStrategy[] = [];
  
  // IndexedDB - best for large data
  strategies.push({
    name: 'indexeddb',
    available: 'indexedDB' in window,
    maxSize: 1024 * 1024 * 1024, // ~1GB typical limit
    persistent: true
  });
  
  // WebSQL (deprecated but still available in some browsers)
  strategies.push({
    name: 'websql',
    available: 'openDatabase' in window,
    maxSize: 50 * 1024 * 1024, // ~50MB typical limit
    persistent: true
  });
  
  // localStorage - fallback for small data only
  strategies.push({
    name: 'localstorage',
    available: 'localStorage' in window,
    maxSize: 10 * 1024 * 1024, // ~10MB typical limit
    persistent: true
  });
  
  // sessionStorage - temporary storage
  strategies.push({
    name: 'sessionstorage',
    available: 'sessionStorage' in window,
    maxSize: 10 * 1024 * 1024, // ~10MB typical limit
    persistent: false
  });
  
  return strategies.filter(s => s.available);
};

// IndexedDB wrapper for mission data
class MissionDataDB {
  private dbName = 'maestro-mission-data';
  private version = 1;
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.version);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };
      
      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        
        // Create object stores
        if (!db.objectStoreNames.contains('missions')) {
          db.createObjectStore('missions', { keyPath: 'id' });
        }
        
        if (!db.objectStoreNames.contains('notes')) {
          const notesStore = db.createObjectStore('notes', { keyPath: 'note_id' });
          notesStore.createIndex('mission_id', 'mission_id', { unique: false });
        }
        
        if (!db.objectStoreNames.contains('logs')) {
          const logsStore = db.createObjectStore('logs', { keyPath: ['mission_id', 'timestamp'] });
          logsStore.createIndex('mission_id', 'mission_id', { unique: false });
        }
        
        if (!db.objectStoreNames.contains('contexts')) {
          db.createObjectStore('contexts', { keyPath: 'mission_id' });
        }
      };
    });
  }

  async storeMission(mission: any): Promise<void> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['missions'], 'readwrite');
      const store = transaction.objectStore('missions');
      
      // Store complete mission data including all fields
      const missionData = {
        id: mission.id,
        request: mission.request,
        status: mission.status,
        plan: mission.plan,
        draft: mission.draft,
        report: mission.report,
        createdAt: mission.createdAt,
        updatedAt: mission.updatedAt,
        stats: mission.stats
      };
      
      const request = store.put(missionData);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve();
    });
  }

  async storeNotes(missionId: string, notes: any[]): Promise<void> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['notes'], 'readwrite');
      const store = transaction.objectStore('notes');
      
      // Clear existing notes for this mission
      const index = store.index('mission_id');
      const deleteRequest = index.openCursor(IDBKeyRange.only(missionId));
      
      deleteRequest.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        } else {
          // Add new notes with validation
          let successCount = 0;
          let totalNotes = 0;
          
          notes.forEach((note, index) => {
            // Ensure note has required fields
            if (!note.note_id) {
              // Generate a note_id if missing
              note.note_id = `${missionId}_note_${Date.now()}_${index}`;
            }
            
            // Ensure timestamp is properly formatted
            if (note.timestamp && !(note.timestamp instanceof Date)) {
              note.timestamp = new Date(note.timestamp);
            }
            
            const noteToStore = { 
              ...note, 
              mission_id: missionId,
              // Ensure all required fields exist
              content: note.content || '',
              timestamp: note.timestamp || new Date()
            };
            
            totalNotes++;
            const putRequest = store.put(noteToStore);
            
            putRequest.onsuccess = () => {
              successCount++;
              if (successCount === totalNotes) {
                resolve();
              }
            };
            
            putRequest.onerror = (error) => {
              console.error('Failed to store individual note:', error, noteToStore);
              
              // Check if this is a key path error and mark for repair
              if (error && error.toString().includes('key path')) {
                try {
                  localStorage.setItem('indexeddb-needs-repair', 'true');
                } catch (e) {
                  console.warn('Could not set repair flag:', e);
                }
              }
              
              successCount++;
              if (successCount === totalNotes) {
                resolve(); // Continue even if some notes fail
              }
            };
          });
          
          // Handle empty notes array
          if (totalNotes === 0) {
            resolve();
          }
        }
      };
      
      deleteRequest.onerror = () => reject(deleteRequest.error);
    });
  }

  async storeLogs(missionId: string, logs: any[]): Promise<void> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['logs'], 'readwrite');
      const store = transaction.objectStore('logs');
      
      // Clear existing logs for this mission
      const index = store.index('mission_id');
      const deleteRequest = index.openCursor(IDBKeyRange.only(missionId));
      
      deleteRequest.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        } else {
          // Add new logs
          logs.forEach(log => {
            store.put({ ...log, mission_id: missionId });
          });
          resolve();
        }
      };
      
      deleteRequest.onerror = () => reject(deleteRequest.error);
    });
  }

  async getMission(missionId: string): Promise<any> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['missions'], 'readonly');
      const store = transaction.objectStore('missions');
      const request = store.get(missionId);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }

  async getNotes(missionId: string): Promise<any[]> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['notes'], 'readonly');
      const store = transaction.objectStore('notes');
      const index = store.index('mission_id');
      const request = index.getAll(missionId);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result || []);
    });
  }

  async getLogs(missionId: string): Promise<any[]> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['logs'], 'readonly');
      const store = transaction.objectStore('logs');
      const index = store.index('mission_id');
      const request = index.getAll(missionId);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result || []);
    });
  }

  async getAllMissions(): Promise<any[]> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['missions'], 'readonly');
      const store = transaction.objectStore('missions');
      const request = store.getAll();
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result || []);
    });
  }

  async clearOldData(keepCount: number = 10): Promise<void> {
    if (!this.db) await this.init();
    
    const missions = await this.getAllMissions();
    const sortedMissions = missions.sort((a, b) => 
      new Date(b.updatedAt || b.createdAt).getTime() - new Date(a.updatedAt || a.createdAt).getTime()
    );
    
    const missionsToDelete = sortedMissions.slice(keepCount);
    
    for (const mission of missionsToDelete) {
      await this.deleteMission(mission.id);
    }
  }

  async deleteMission(missionId: string): Promise<void> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['missions', 'notes', 'logs', 'contexts'], 'readwrite');
      
      // Delete mission
      transaction.objectStore('missions').delete(missionId);
      
      // Delete notes
      const notesIndex = transaction.objectStore('notes').index('mission_id');
      const notesRequest = notesIndex.openCursor(IDBKeyRange.only(missionId));
      notesRequest.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        }
      };
      
      // Delete logs
      const logsIndex = transaction.objectStore('logs').index('mission_id');
      const logsRequest = logsIndex.openCursor(IDBKeyRange.only(missionId));
      logsRequest.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        }
      };
      
      // Delete contexts
      transaction.objectStore('contexts').delete(missionId);
      
      transaction.onerror = () => reject(transaction.error);
      transaction.oncomplete = () => resolve();
    });
  }

  async clearCorruptedData(): Promise<void> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['notes'], 'readwrite');
      const store = transaction.objectStore('notes');
      
      // Find and delete notes without valid note_id
      const request = store.openCursor();
      
      request.onsuccess = (event) => {
        const cursor = (event.target as IDBRequest).result;
        if (cursor) {
          const note = cursor.value;
          
          // Check if note has invalid data
          if (!note.note_id || typeof note.note_id !== 'string' || note.note_id.trim() === '') {
            console.warn('Deleting corrupted note:', note);
            cursor.delete();
          }
          
          cursor.continue();
        } else {
          console.log('Finished cleaning corrupted notes data');
          resolve();
        }
      };
      
      request.onerror = () => reject(request.error);
    });
  }

  async repairDatabase(): Promise<void> {
    try {
      console.log('Starting IndexedDB repair...');
      
      // Clear corrupted data
      await this.clearCorruptedData();
      
      // Validate and fix existing notes
      const missions = await this.getAllMissions();
      
      for (const mission of missions) {
        try {
          const notes = await this.getNotes(mission.id);
          
          // Validate and fix notes
          const validatedNotes = notes.map((note, index) => ({
            ...note,
            note_id: note.note_id || `${mission.id}_repair_${Date.now()}_${index}`,
            content: note.content || '',
            timestamp: note.timestamp instanceof Date ? note.timestamp : new Date(note.timestamp || Date.now()),
            mission_id: mission.id
          }));
          
          // Re-store validated notes
          if (validatedNotes.length > 0) {
            await this.storeNotes(mission.id, validatedNotes);
          }
        } catch (error) {
          console.error(`Failed to repair notes for mission ${mission.id}:`, error);
        }
      }
      
      console.log('IndexedDB repair completed');
    } catch (error) {
      console.error('Failed to repair IndexedDB:', error);
    }
  }
}

// Global instance
const missionDB = new MissionDataDB();

// Enhanced storage management
export const clearOldStorageData = () => {
  try {
    // Only clear localStorage quota issues, not data truncation
    const testKey = 'storage-test';
    const testData = 'x'.repeat(1024); // 1KB test data
    
    try {
      localStorage.setItem(testKey, testData);
      localStorage.removeItem(testKey);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.warn('LocalStorage quota exceeded, migrating to IndexedDB...');
        
        // Migrate mission data to IndexedDB instead of truncating
        migrateMissionDataToIndexedDB();
        
        // Clear only localStorage mission data after migration
        localStorage.removeItem('mission-storage');
        
        console.log('Migrated mission data to IndexedDB due to localStorage quota');
      }
    }
  } catch (error) {
    console.error('Error checking storage capacity:', error);
  }
};

// Migration function
const migrateMissionDataToIndexedDB = async () => {
  try {
    const missionData = localStorage.getItem('mission-storage');
    if (!missionData) return;
    
    const parsed = JSON.parse(missionData);
    if (!parsed.missions) return;
    
    await missionDB.init();
    
    // Migrate each mission
    for (const mission of parsed.missions) {
      await missionDB.storeMission(mission);
      
      if (mission.notes) {
        await missionDB.storeNotes(mission.id, mission.notes);
      }
    }
    
    // Migrate logs
    if (parsed.missionLogs) {
      for (const [missionId, logs] of Object.entries(parsed.missionLogs)) {
        await missionDB.storeLogs(missionId, logs as any[]);
      }
    }
    
    console.log('Successfully migrated mission data to IndexedDB');
  } catch (error) {
    console.error('Failed to migrate mission data:', error);
  }
};

export const getStorageUsage = () => {
  try {
    let totalSize = 0;
    const usage: Record<string, number> = {};
    
    for (let key in localStorage) {
      if (localStorage.hasOwnProperty(key)) {
        const value = localStorage.getItem(key);
        if (value) {
          const size = new Blob([value]).size;
          usage[key] = size;
          totalSize += size;
        }
      }
    }
    
    return {
      totalSize,
      usage,
      totalSizeMB: (totalSize / (1024 * 1024)).toFixed(2),
      strategies: getAvailableStorageStrategies()
    };
  } catch (error) {
    console.error('Error calculating storage usage:', error);
    return { totalSize: 0, usage: {}, totalSizeMB: '0', strategies: [] };
  }
};

export const logStorageUsage = () => {
  const usage = getStorageUsage();
  // console.log('Storage usage:', usage);
  
  // Log available strategies
  // console.log('Available storage strategies:', usage.strategies);
  
  // Warn if localStorage usage is high
  if (usage.totalSize > 5 * 1024 * 1024) { // 5MB
    console.warn('LocalStorage usage is high:', usage.totalSizeMB + 'MB');
    console.log('Consider using IndexedDB for large data storage');
  }
};

// Enhanced safe localStorage operations with automatic fallback
export const safeSetItem = (key: string, value: string): boolean => {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      console.warn('LocalStorage quota exceeded, attempting migration...');
      
      // If this is mission data, migrate to IndexedDB
      if (key === 'mission-storage') {
        migrateMissionDataToIndexedDB().then(() => {
          localStorage.removeItem(key);
          console.log('Mission data migrated to IndexedDB');
        });
        return false; // Don't store in localStorage
      }
      
      // For other data, try to clear old data
      clearOldStorageData();
      
      // Retry once
      try {
        localStorage.setItem(key, value);
        return true;
      } catch (retryError) {
        console.error('Failed to save to localStorage after cleanup:', retryError);
        return false;
      }
    }
    console.error('Failed to save to localStorage:', error);
    return false;
  }
};

// IndexedDB-aware storage interface
export const hybridStorage = {
  // For mission data, use IndexedDB
  async setMissionData( data: any): Promise<void> {
    await missionDB.storeMission(data);
  },
  
  async getMissionData(missionId: string): Promise<any> {
    return await missionDB.getMission(missionId);
  },
  
  async setMissionNotes(missionId: string, notes: any[]): Promise<void> {
    await missionDB.storeNotes(missionId, notes);
  },
  
  async getMissionNotes(missionId: string): Promise<any[]> {
    return await missionDB.getNotes(missionId);
  },
  
  async setMissionLogs(missionId: string, logs: any[]): Promise<void> {
    await missionDB.storeLogs(missionId, logs);
  },
  
  async getMissionLogs(missionId: string): Promise<any[]> {
    return await missionDB.getLogs(missionId);
  },
  
  async getAllMissions(): Promise<any[]> {
    return await missionDB.getAllMissions();
  },
  
  async clearOldMissions(keepCount: number = 10): Promise<void> {
    await missionDB.clearOldData(keepCount);
  },
  
  // For small data, use localStorage
  setSmallData(key: string, value: any): boolean {
    try {
      return safeSetItem(key, JSON.stringify(value));
    } catch (error) {
      console.error('Failed to store small data:', error);
      return false;
    }
  },
  
  getSmallData(key: string): any {
    try {
      const value = localStorage.getItem(key);
      return value ? JSON.parse(value) : null;
    } catch (error) {
      console.error('Failed to retrieve small data:', error);
      return null;
    }
  }
};

// Initialize hybrid storage
export const initHybridStorage = async () => {
  try {
    await missionDB.init();
    // console.log('IndexedDB initialized for mission data storage');
    
    // Check if we need to migrate existing localStorage data
    const existingMissionData = localStorage.getItem('mission-storage');
    if (existingMissionData) {
      console.log('Found existing mission data in localStorage, checking if migration is needed...');
      const parsed = JSON.parse(existingMissionData);
      if (parsed.missions && parsed.missions.length > 0) {
        console.log('Migrating existing mission data to IndexedDB...');
        await migrateMissionDataToIndexedDB();
      }
    }
    
    // Check for and repair any corrupted data
    const shouldRepair = localStorage.getItem('indexeddb-needs-repair');
    if (shouldRepair === 'true') {
      console.log('Repairing IndexedDB due to previous errors...');
      await missionDB.repairDatabase();
      localStorage.removeItem('indexeddb-needs-repair');
    }
    
    logStorageUsage();
  } catch (error) {
    console.error('Failed to initialize hybrid storage:', error);
    console.log('Falling back to localStorage only');
    
    // Mark for repair on next load
    try {
      localStorage.setItem('indexeddb-needs-repair', 'true');
    } catch (e) {
      console.warn('Could not set repair flag:', e);
    }
  }
};

// Export the mission database for direct use
export { missionDB };
