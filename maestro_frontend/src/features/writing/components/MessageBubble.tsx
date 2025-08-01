import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { Copy, RotateCcw, Check, Bot, User, Trash2 } from 'lucide-react'
import { formatChatMessageTime } from '../../../utils/timezone'
import { SourceBubbles } from './SourceBubbles'
import type { Source } from '../api'

interface MessageBubbleProps {
  message: {
    id: string
    role: 'user' | 'assistant'
    content: string
    timestamp: Date | string
    sources?: Source[]
  }
  onRegenerate?: () => void
  onDelete?: () => void
  isRegenerating?: boolean
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onRegenerate,
  onDelete,
  isRegenerating = false
}) => {
  const [copiedContent, setCopiedContent] = useState<string | null>(null)
  const [hoveredCodeBlock, setHoveredCodeBlock] = useState<string | null>(null)

  const copyToClipboard = async (text: string, type: 'message' | 'code' = 'message') => {
    try {
      // Check if clipboard API is available
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        // Fallback for older browsers or insecure contexts
        const textArea = document.createElement('textarea')
        textArea.value = text
        textArea.style.position = 'fixed'
        textArea.style.left = '-999999px'
        textArea.style.top = '-999999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }
      
      setCopiedContent(type === 'message' ? 'message' : text)
      setTimeout(() => setCopiedContent(null), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
      // Still show success feedback even if copy failed
      setCopiedContent(type === 'message' ? 'message' : text)
      setTimeout(() => setCopiedContent(null), 2000)
    }
  }

  const isUserMessage = message.role === 'user'

  // Parse content blocks and regular content
  const { contentBlocks, regularContent } = React.useMemo(() => {
    let content = message.content
    
    // Check if the entire content is wrapped in a markdown code block first
    const markdownCodeBlockRegex = /^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$/
    const markdownMatch = content.match(markdownCodeBlockRegex)
    
    if (markdownMatch) {
      content = markdownMatch[1].trim()
    }
    
    // Extract content blocks
    const contentBlockRegex = /```content-block:(\w+)\s*\n([\s\S]*?)\n```/g
    const blocks: Array<{type: string, content: string, id: string}> = []
    let match
    
    while ((match = contentBlockRegex.exec(content)) !== null) {
      blocks.push({
        type: match[1],
        content: match[2].trim(),
        id: `block-${Math.random().toString(36).substr(2, 9)}`
      })
    }
    
    // Remove content blocks from regular content
    const cleanContent = content.replace(contentBlockRegex, '').trim()
    
    return {
      contentBlocks: blocks,
      regularContent: cleanContent
    }
  }, [message.content])

  return (
    <div className={`flex ${isUserMessage ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex ${
        isUserMessage 
          ? 'max-w-xs lg:max-w-md flex-row-reverse' 
          : 'max-w-full flex-row'
      } items-start space-x-3`}>
        {/* Avatar */}
        <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
          isUserMessage 
            ? 'bg-primary text-primary-foreground ml-2' 
            : 'bg-muted mr-2'
        }`}>
          {isUserMessage ? (
            <User className="h-3.5 w-3.5" />
          ) : (
            <Bot className="h-3.5 w-3.5 text-text-secondary" />
          )}
        </div>
        
        {/* Message Container */}
        <div className={`relative group min-w-0 ${
          isUserMessage
            ? 'max-w-xs lg:max-w-md'
            : 'flex-1'
        }`}>
          <div className="absolute top-1.5 right-1.5 flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <button
              onClick={() => copyToClipboard(message.content)}
              className="bg-background border border-border rounded-md p-1 shadow-sm hover:bg-muted z-10 transition-colors duration-150"
              title="Copy message"
            >
              {copiedContent === 'message' ? (
                <Check className="h-2.5 w-2.5 text-green-500" />
              ) : (
                <Copy className="h-2.5 w-2.5 text-text-secondary" />
              )}
            </button>
            {onDelete && (
              <button
                onClick={onDelete}
                className="bg-background border border-border rounded-md p-1 shadow-sm hover:bg-destructive/10 hover:border-destructive/20 z-10 transition-colors duration-150"
                title="Delete message"
              >
                <Trash2 className="h-2.5 w-2.5 text-destructive" />
              </button>
            )}
          </div>

          {/* Message Bubble */}
          <div className={`px-3 py-2 rounded-xl ${
            isUserMessage
              ? 'bg-primary text-primary-foreground rounded-br-md'
              : 'bg-card border border-border text-text-primary rounded-bl-md shadow-sm'
          }`}>
            <div className="prose prose-xs max-w-none text-current break-words text-sm">
              {/* Render regular content if any */}
              {regularContent && (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    // Links
                    a: ({node, ...props}) => (
                      <a 
                        {...props} 
                        target="_blank" 
                        rel="noopener noreferrer" 
                        className={isUserMessage ? "text-primary-foreground/80 hover:underline" : "text-primary hover:underline"}
                      />
                    ),
                    
                    // Lists
                    ul: ({node, ...props}) => <ul {...props} className="my-1 space-y-0.5" />,
                    ol: ({node, ...props}) => <ol {...props} className="my-1 space-y-0.5" />,
                    li: ({node, ...props}) => <li {...props} className="ml-4" />,
                    
                    // Paragraphs
                    p: ({node, ...props}) => <p {...props} className="mb-1 last:mb-0 break-words leading-relaxed" />,
                    
                    // Headings
                    h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-1 mt-2 first:mt-0" />,
                    h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-1 mt-1.5 first:mt-0" />,
                    h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-0.5 mt-1 first:mt-0" />,
                    h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                    h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                    h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium mb-0.5 mt-0.5 first:mt-0" />,
                    
                    // Blockquotes
                    blockquote: ({node, ...props}) => (
                      <blockquote 
                        {...props} 
                        className={`border-l-4 pl-4 my-1.5 italic ${
                          isUserMessage ? 'border-primary-foreground/50' : 'border-border'
                        }`} 
                      />
                    ),
                    
                    // Tables
                    table: ({node, ...props}) => (
                      <div className="overflow-x-auto my-3">
                        <table {...props} className="min-w-full border-collapse border border-border" />
                      </div>
                    ),
                    th: ({node, ...props}) => (
                      <th {...props} className="border border-border px-3 py-2 bg-muted font-medium text-left" />
                    ),
                    td: ({node, ...props}) => (
                      <td {...props} className="border border-border px-3 py-2" />
                    ),
                    
                    // Inline code
                    code: ({node, className, children, ...props}) => {
                      const match = /language-(\w+)/.exec(className || '')
                      const isInline = !match
                      const codeContent = String(children).replace(/\n$/, '')
                      
                      if (isInline) {
                        return (
                          <code 
                            {...props} 
                            className={`px-1 py-0.5 rounded text-xs font-mono ${
                              isUserMessage 
                                ? 'bg-primary-foreground/20 text-primary-foreground' 
                                : 'bg-muted text-text-primary'
                            }`}
                          >
                            {children}
                          </code>
                        )
                      }
                      
                      // Code block with copy button
                      const blockId = `code-${Math.random().toString(36).substr(2, 9)}`
                      
                      return (
                        <div 
                          className="relative group/code my-3"
                          onMouseEnter={() => setHoveredCodeBlock(blockId)}
                          onMouseLeave={() => setHoveredCodeBlock(null)}
                        >
                          {/* Copy button for code block */}
                          <button
                            onClick={() => copyToClipboard(codeContent, 'code')}
                            className={`absolute top-1.5 right-1.5 transition-opacity duration-200 bg-gray-700 hover:bg-gray-600 text-white rounded p-1 text-xs ${
                              hoveredCodeBlock === blockId ? 'opacity-100' : 'opacity-0'
                            }`}
                            title="Copy code"
                          >
                            {copiedContent === codeContent ? (
                              <Check className="h-2.5 w-2.5" />
                            ) : (
                              <Copy className="h-2.5 w-2.5" />
                            )}
                          </button>
                          
                          <pre className="bg-code-background text-code-foreground p-3 rounded-lg overflow-x-auto">
                            <code className="text-xs font-mono whitespace-pre">
                              {children}
                            </code>
                          </pre>
                          
                          {match && (
                            <div className="text-xs text-text-tertiary mt-1 font-mono">
                              {match[1]}
                            </div>
                          )}
                        </div>
                      )
                    },
                    
                    // Pre blocks (fallback)
                    pre: ({node, children, ...props}) => {
                      // If it's already handled by code component, don't double-wrap
                      if (React.isValidElement(children) && children.type === 'code') {
                        return <>{children}</>
                      }
                      
                      return (
                        <pre 
                          {...props} 
                          className="bg-code-background text-code-foreground p-3 rounded-lg overflow-x-auto my-2 text-xs font-mono whitespace-pre-wrap"
                        >
                          {children}
                        </pre>
                      )
                    },
                    
                    // Horizontal rules
                    hr: ({node, ...props}) => (
                      <hr {...props} className="my-1.5 border-border" />
                    ),
                  }}
                >
                  {regularContent}
                </ReactMarkdown>
              )}

              {/* Render content blocks with individual copy buttons */}
              {contentBlocks.map((block) => (
                <div key={block.id} className="relative my-3 group/content-block">
                  {/* Content block copy button */}
                  <button
                    onClick={() => copyToClipboard(block.content, 'code')}
                    className="absolute top-1.5 right-1.5 z-10 bg-background border border-border rounded-md p-1 shadow-sm hover:bg-muted opacity-100"
                    title={`Copy ${block.type} content`}
                  >
                    {copiedContent === block.content ? (
                      <Check className="h-2.5 w-2.5 text-green-500" />
                    ) : (
                      <Copy className="h-2.5 w-2.5 text-text-secondary" />
                    )}
                  </button>

                  {/* Content block container */}
                  <div className="border border-border rounded-lg p-3 bg-muted">
                    <div className="text-xs text-text-tertiary mb-1.5 font-mono uppercase">
                      {block.type} content
                    </div>
                    <div className="prose prose-xs max-w-none">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          // Same components as above but simplified for content blocks
                          a: ({node, ...props}) => (
                            <a {...props} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline" />
                          ),
                          ul: ({node, ...props}) => <ul {...props} className="my-2 space-y-1" />,
                          ol: ({node, ...props}) => <ol {...props} className="my-2 space-y-1" />,
                          li: ({node, ...props}) => <li {...props} className="ml-4" />,
                          p: ({node, ...props}) => <p {...props} className="mb-2 last:mb-0 break-words leading-relaxed" />,
                          h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-2 mt-3 first:mt-0" />,
                          h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-2 mt-2 first:mt-0" />,
                          h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-1 mt-2 first:mt-0" />,
                          h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                          h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                          h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                          blockquote: ({node, ...props}) => (
                            <blockquote {...props} className="border-l-4 border-border pl-4 my-3 italic" />
                          ),
                          code: ({node, className, children, ...props}) => {
                            const match = /language-(\w+)/.exec(className || '')
                            const isInline = !match
                            
                            if (isInline) {
                              return (
                                <code {...props} className="px-1 py-0.5 rounded text-xs font-mono bg-background text-text-primary">
                                  {children}
                                </code>
                              )
                            }
                            
                            return (
                              <pre className="bg-code-background text-code-foreground p-3 rounded-lg overflow-x-auto my-2">
                                <code className="text-xs font-mono whitespace-pre">
                                  {children}
                                </code>
                              </pre>
                            )
                          },
                        }}
                      >
                        {block.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              ))}

              {/* Fallback: render original content if no blocks found and no regular content */}
              {contentBlocks.length === 0 && !regularContent && (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    // Same components as the first ReactMarkdown instance
                    a: ({node, ...props}) => (
                      <a 
                        {...props} 
                        target="_blank" 
                        rel="noopener noreferrer" 
                        className={isUserMessage ? "text-primary-foreground/80 hover:underline" : "text-primary hover:underline"}
                      />
                    ),
                    p: ({node, ...props}) => <p {...props} className="mb-2 last:mb-0 break-words leading-relaxed" />,
                    h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-2 mt-3 first:mt-0" />,
                    h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-2 mt-2 first:mt-0" />,
                    h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-1 mt-2 first:mt-0" />,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              )}
            </div>
            
            {/* Sources for assistant messages */}
            {!isUserMessage && message.sources && message.sources.length > 0 && (
              <SourceBubbles sources={message.sources} />
            )}
            
            {/* Timestamp */}
            <p className={`text-xs mt-1 ${
              isUserMessage ? 'text-primary-foreground/70' : 'text-text-tertiary'
            }`} style={{ fontSize: '0.7rem', opacity: 0.8 }}>
              {formatChatMessageTime(message.timestamp)}
            </p>
          </div>

          {/* Action buttons for assistant messages - Always visible */}
          {!isUserMessage && (
            <div className="flex items-center justify-end space-x-1.5 mt-1.5">
              {onRegenerate && (
                <button
                  onClick={onRegenerate}
                  disabled={isRegenerating}
                  className="flex items-center space-x-1 px-1.5 py-0.5 text-xs text-text-secondary hover:text-text-primary hover:bg-muted rounded transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Regenerate response"
                >
                  <RotateCcw className={`h-2.5 w-2.5 ${isRegenerating ? 'animate-spin' : ''}`} />
                  <span>Regenerate</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
