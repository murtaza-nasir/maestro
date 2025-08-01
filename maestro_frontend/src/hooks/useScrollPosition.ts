import { useRef, useEffect, useCallback } from 'react'

interface UseScrollPositionOptions {
  key: string
  dependencies?: any[]
}

export const useScrollPosition = ({ key, dependencies = [] }: UseScrollPositionOptions) => {
  const scrollPositions = useRef<Record<string, number>>({})
  const containerRef = useRef<HTMLDivElement | null>(null)

  const saveScrollPosition = useCallback(() => {
    if (containerRef.current) {
      scrollPositions.current[key] = containerRef.current.scrollTop
    }
  }, [key])

  const restoreScrollPosition = useCallback(() => {
    if (containerRef.current) {
      const savedPosition = scrollPositions.current[key] || 0
      containerRef.current.scrollTop = savedPosition
    }
  }, [key])

  // Save scroll position when dependencies change
  useEffect(() => {
    return () => {
      saveScrollPosition()
    }
  }, dependencies)

  // Restore scroll position after dependencies change
  useEffect(() => {
    const timer = setTimeout(() => {
      restoreScrollPosition()
    }, 0)
    return () => clearTimeout(timer)
  }, dependencies)

  return {
    containerRef,
    saveScrollPosition,
    restoreScrollPosition
  }
}
