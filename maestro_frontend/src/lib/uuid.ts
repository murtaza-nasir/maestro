/**
 * Generate a UUID v4 string
 * Uses crypto.randomUUID() when available (secure contexts),
 * falls back to a polyfill for local network environments
 */
export function generateUUID(): string {
  // Try to use the native crypto.randomUUID if available
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    try {
      return crypto.randomUUID()
    } catch (error) {
      // Fall through to polyfill if crypto.randomUUID fails
    }
  }
  
  // Polyfill for environments without crypto.randomUUID
  // This is especially important for local network deployments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}
