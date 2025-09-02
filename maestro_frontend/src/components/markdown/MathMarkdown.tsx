import React, { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import './MathMarkdown.css'

interface MathMarkdownProps {
  content: string
  className?: string
  components?: any
}

/**
 * A wrapper component for ReactMarkdown that handles KaTeX CSS loading
 * in a way that doesn't break parent container scrolling.
 * 
 * The problem: Loading KaTeX CSS globally affects parent container heights
 * The solution: Load KaTeX CSS dynamically and scope it to this component
 */
export const MathMarkdown: React.FC<MathMarkdownProps> = ({ 
  content, 
  className = '',
  components = {}
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    // Dynamically load KaTeX CSS only if we detect math content
    if (content && (content.includes('$') || content.includes('\\('))) {
      // Check if KaTeX CSS is already loaded
      const existingKatexLink = document.querySelector('link[href*="katex.min.css"]')
      
      if (!existingKatexLink) {
        const link = document.createElement('link')
        link.rel = 'stylesheet'
        link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'
        link.crossOrigin = 'anonymous'
        document.head.appendChild(link)
        
        // Clean up on unmount
        return () => {
          // Don't remove as other components might be using it
        }
      }
    }
  }, [content])
  
  return (
    <div ref={containerRef} className={`math-markdown-container ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        components={components}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  )
}