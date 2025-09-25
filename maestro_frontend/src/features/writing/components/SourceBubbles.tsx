import React, { useState } from 'react'
import { Globe, FileText } from 'lucide-react'
import type { Source, DocumentSource } from '../api'
import { DocumentViewModal } from '../../documents/components/DocumentViewModal'
import { getDocument } from '../../documents/api'
import type { Document } from '../../documents/types'

interface SourceBubblesProps {
  sources: Source[]
}

export const SourceBubbles: React.FC<SourceBubblesProps> = ({ sources }) => {
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isLoadingDoc, setIsLoadingDoc] = useState(false)

  if (!sources || sources.length === 0) {
    return null
  }

  const handleWebSourceClick = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const handleDocumentSourceClick = async (docId: string) => {
    setIsLoadingDoc(true)
    try {
      const doc = await getDocument(docId)
      setSelectedDocument(doc)
      setIsModalOpen(true)
    } catch (error) {
      console.error('Failed to load document:', error)
      // Could show a toast here if needed
    } finally {
      setIsLoadingDoc(false)
    }
  }

  return (
    <>
      <div className="mt-3 flex flex-wrap gap-2">
        {sources.map((source, index) => {
          const isWebSource = source.type === 'web'
          const isDocSource = source.type === 'document'
          // Use the reference_number from backend if available, otherwise use index + 1
          const referenceNumber = (source as any).reference_number || index + 1
          
          const handleClick = () => {
            if (isWebSource) {
              handleWebSourceClick((source as any).url)
            } else if (isDocSource) {
              const docSource = source as DocumentSource
              handleDocumentSourceClick(docSource.doc_id)
            }
          }
          
          return (
            <div
              key={index}
              className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ${
                isWebSource
                  ? 'bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer'
                  : 'bg-green-500/10 text-green-500 hover:bg-green-500/20 cursor-pointer'
              }`}
              onClick={handleClick}
              title={source.title}
            >
            {/* Reference Number */}
            <span className="font-bold mr-1.5">
              [{referenceNumber}]
            </span>
            
            {/* Icon */}
            <div className="mr-1.5">
              {isWebSource ? (
                <Globe className="h-3 w-3" />
              ) : (
                <FileText className="h-3 w-3" />
              )}
            </div>
            
            {/* Title */}
            <span className="truncate max-w-[120px]">
              {source.title}
            </span>
          </div>
        )
      })}
    </div>
    
    {/* Document View Modal */}
    <DocumentViewModal
      document={selectedDocument}
      isOpen={isModalOpen}
      onClose={() => {
        setIsModalOpen(false)
        setSelectedDocument(null)
      }}
    />
    </>
  )
}
