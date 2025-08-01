/**
 * Timezone utilities for consistent timestamp formatting across the application
 * 
 * The backend stores timestamps in UTC, but we want to display them in the server's timezone (America/Chicago)
 * to match the Docker container's TZ environment variable.
 */

// Server timezone - should match the TZ environment variable in docker-compose.yml
export const SERVER_TIMEZONE = import.meta.env.VITE_SERVER_TIMEZONE || 'America/Chicago';

/**
 * Ensure a timestamp is a proper Date object with correct timezone handling
 * @param timestamp - Date object or ISO string
 * @returns Date object
 */
export const ensureDate = (timestamp: Date | string): Date => {
  if (typeof timestamp === 'string') {
    // Check if the string already includes timezone information
    if (timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-')) {
      // It's already an ISO string with timezone info, so we can parse it directly
      return new Date(timestamp);
    } else {
      // It's a date string without timezone, assume it's in server timezone
      // Format: YYYY-MM-DDTHH:MM:SS
      return new Date(`${timestamp} ${SERVER_TIMEZONE}`);
    }
  }
  return timestamp;
};

/**
 * Format a timestamp to display in the server's timezone
 * @param timestamp - Date object or ISO string
 * @param options - Intl.DateTimeFormatOptions
 * @returns Formatted time string in server timezone
 */
export const formatTimeInServerTimezone = (
  timestamp: Date | string | null | undefined,
  options: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }
): string => {
  if (!timestamp || timestamp === 'undefined') {
    return "Invalid Date";
  }
  try {
    // Ensure we have a proper Date object
    const date = ensureDate(timestamp);
    
    // Add logging
    // console.log('Formatting timestamp:', {
    //   input: timestamp,
    //   dateObject: date,
    //   dateISOString: date.toISOString(),
    //   dateGetTime: date.getTime(),
    //   serverTimezone: SERVER_TIMEZONE,
    //   options
    // });
    
    // Format using the server's timezone
    const formatted = new Intl.DateTimeFormat('en-US', {
      ...options,
      timeZone: SERVER_TIMEZONE
    }).format(date);
    
    // console.log('Formatted result:', formatted);
    
    return formatted;
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return "Invalid Date";
  }
};

/**
 * Format a timestamp for chat messages with smart date/time display
 * - Today: Just time (e.g., "2:30 PM")
 * - This year but not today: Date and time (e.g., "Jul 28, 2:30 PM")
 * - Previous years: Full date and time (e.g., "Jul 28, 2024, 2:30 PM")
 * @param timestamp - Date object or ISO string (assumed to be UTC)
 * @returns Formatted time string in server timezone
 */
export const formatChatMessageTime = (timestamp: Date | string): string => {
  if (!timestamp || timestamp === 'undefined') {
    return "Invalid Date";
  }
  
  try {
    const date = ensureDate(timestamp);
    const now = new Date();
    
    // Get dates in server timezone for comparison
    const messageDate = new Date(date.toLocaleString("en-US", { timeZone: SERVER_TIMEZONE }));
    const todayDate = new Date(now.toLocaleString("en-US", { timeZone: SERVER_TIMEZONE }));
    
    // Check if it's today
    const isToday = messageDate.toDateString() === todayDate.toDateString();
    
    // Check if it's this year
    const isThisYear = messageDate.getFullYear() === todayDate.getFullYear();
    
    if (isToday) {
      // Just show time for today's messages
      return formatTimeInServerTimezone(timestamp, {
        hour: '2-digit',
        minute: '2-digit'
      });
    } else if (isThisYear) {
      // Show month, day, and time for this year's messages
      return formatTimeInServerTimezone(timestamp, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } else {
      // Show full date and time for previous years
      return formatTimeInServerTimezone(timestamp, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  } catch (error) {
    console.error('Error formatting chat message time:', error);
    return "Invalid Date";
  }
};

/**
 * Format a timestamp for chat messages (without seconds) - Legacy function
 * @param timestamp - Date object or ISO string (assumed to be UTC)
 * @returns Formatted time string in server timezone (HH:MM AM/PM)
 */
export const formatChatMessageTimeOnly = (timestamp: Date | string): string => {
  return formatTimeInServerTimezone(timestamp, {
    hour: '2-digit',
    minute: '2-digit'
  });
};

/**
 * Format a timestamp for activity logs (with seconds)
 * @param timestamp - Date object or ISO string (assumed to be UTC)
 * @returns Formatted time string in server timezone (HH:MM:SS AM/PM)
 */
export const formatActivityLogTime = (timestamp: Date | string): string => {
  return formatTimeInServerTimezone(timestamp, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

/**
 * Format a full date and time in server timezone
 * @param timestamp - Date object or ISO string (assumed to be UTC)
 * @returns Formatted date and time string
 */
export const formatFullDateTime = (timestamp: Date | string | null | undefined): string => {
  if (!timestamp || timestamp === 'undefined') {
    return "Invalid Date";
  }
  try {
    // Ensure we have a proper Date object
    const date = ensureDate(timestamp);
    
    // Add logging
    // console.log('Formatting full datetime:', {
    //   input: timestamp,
    //   dateObject: date,
    //   dateISOString: date.toISOString(),
    //   dateGetTime: date.getTime(),
    //   serverTimezone: SERVER_TIMEZONE
    // });
    
    // Format using the server's timezone with Intl.DateTimeFormat for consistency
    const formatted = new Intl.DateTimeFormat('en-US', {
      timeZone: SERVER_TIMEZONE,
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    }).format(date);
    
    // console.log('Formatted full datetime result:', formatted);
    
    return formatted;
  } catch (error) {
    console.error('Error formatting full datetime:', error);
    return "Invalid Date";
  }
};
