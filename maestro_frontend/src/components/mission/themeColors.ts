// Theme-aware color utilities for mission components
// These classes work with both light and dark modes

export const themeColors = {
  // Backgrounds
  bgPrimary: 'bg-background',
  bgSecondary: 'bg-secondary',
  bgCard: 'bg-card',
  bgMuted: 'bg-muted',
  
  // Borders
  border: 'border-border',
  borderMuted: 'border-muted',
  
  // Text
  textPrimary: 'text-foreground',
  textSecondary: 'text-muted-foreground',
  textAccent: 'text-accent-foreground',
  
  // Research Agent specific - blue theme
  researchBg: 'bg-blue-50 dark:bg-blue-950/20',
  researchBorder: 'border-blue-200 dark:border-blue-800',
  researchText: 'text-blue-800 dark:text-blue-200',
  researchTextSecondary: 'text-blue-600 dark:text-blue-400',
  researchAccent: 'text-blue-700 dark:text-blue-300',
  researchCard: 'bg-white dark:bg-slate-900',
  
  // Success/New Questions - green theme
  successBg: 'bg-green-50 dark:bg-green-950/20',
  successBorder: 'border-green-200 dark:border-green-800',
  successText: 'text-green-600 dark:text-green-400',
  successAccent: 'border-green-400 dark:border-green-600',
  
  // Warning/Scratchpad - amber theme
  warningBg: 'bg-amber-50 dark:bg-amber-950/20',
  warningBorder: 'border-amber-200 dark:border-amber-800',
  warningText: 'text-amber-800 dark:text-amber-200',
  warningTextSecondary: 'text-amber-700 dark:text-amber-300',
  warningAccent: 'border-amber-400 dark:border-amber-600',
  
  // General content cards
  contentCard: 'bg-white dark:bg-gray-900',
  contentBorder: 'border-gray-200 dark:border-gray-700',
  contentText: 'text-gray-700 dark:text-gray-300',
  contentMuted: 'text-gray-500 dark:text-gray-400',
  contentHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
  
  // Code/Mono backgrounds
  codeBg: 'bg-gray-100 dark:bg-gray-800',
  codeText: 'text-gray-800 dark:text-gray-200',
  
  // Badge/Tag styles
  badge: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300',
  badgeSecondary: 'bg-secondary text-secondary-foreground',
  
  // Planning Agent - purple theme
  planningBg: 'bg-purple-50 dark:bg-purple-950/20',
  planningBorder: 'border-purple-200 dark:border-purple-800',
  planningText: 'text-purple-800 dark:text-purple-200',
  planningAccent: 'text-purple-600 dark:text-purple-400',
  
  // Writing Agent - emerald theme
  writingBg: 'bg-emerald-50 dark:bg-emerald-950/20',
  writingBorder: 'border-emerald-200 dark:border-emerald-800',
  writingText: 'text-emerald-800 dark:text-emerald-200',
  writingAccent: 'text-emerald-600 dark:text-emerald-400',
  
  // Reflection Agent - orange theme
  reflectionBg: 'bg-orange-50 dark:bg-orange-950/20',
  reflectionBorder: 'border-orange-200 dark:border-orange-800',
  reflectionText: 'text-orange-800 dark:text-orange-200',
  reflectionAccent: 'text-orange-600 dark:text-orange-400',
  
  // Tool Call Renderer
  toolBg: 'bg-gray-50 dark:bg-gray-900',
  toolBorder: 'border-gray-100 dark:border-gray-800',
  toolHeader: 'bg-gray-100 dark:bg-gray-800',
};