/**
 * Utility functions for cleaning and formatting log data
 */

/**
 * Remove technical implementation details from log data
 */
export function cleanLogData(data: any): any {
  if (!data || typeof data !== 'object') {
    return data;
  }

  if (Array.isArray(data)) {
    return data.map(cleanLogData);
  }

  const cleaned = { ...data };
  
  // Remove technical implementation details
  delete cleaned.update_callback;
  delete cleaned.log_queue;
  
  // Recursively clean nested objects
  for (const key in cleaned) {
    if (cleaned[key] && typeof cleaned[key] === 'object') {
      cleaned[key] = cleanLogData(cleaned[key]);
    }
  }
  
  return cleaned;
}

/**
 * Safely stringify log data with technical details removed
 */
export function stringifyCleanLogData(data: any, space?: number): string {
  const cleaned = cleanLogData(data);
  return JSON.stringify(cleaned, null, space);
}
