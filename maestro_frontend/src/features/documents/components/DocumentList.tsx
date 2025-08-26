import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type { Document } from '../types';
import { Button } from '../../../components/ui/button';
import { Paperclip, Trash2, FileText, Calendar, BookOpen, Eye, Edit } from 'lucide-react';
import { DocumentMetadataEditModal } from './DocumentMetadataEditModal';
import { DocumentViewModal } from './DocumentViewModal';

interface DocumentListProps {
  documents: Document[];
  onUpload: (file: File) => void;
  onDelete: (documentId: string) => void;
  onDocumentUpdated?: () => void;
}

const DocumentList: React.FC<DocumentListProps> = ({ documents, onUpload, onDelete, onDocumentUpdated }) => {
  const { t } = useTranslation();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);

  const handleEditDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setEditModalOpen(true);
  }, []);

  const handleViewDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setViewModalOpen(true);
  }, []);

  const handleCloseModals = useCallback(() => {
    setEditModalOpen(false);
    setViewModalOpen(false);
    setSelectedDocument(null);
  }, []);

  const handleDocumentUpdated = useCallback(() => {
    handleCloseModals();
    onDocumentUpdated?.();
  }, [handleCloseModals, onDocumentUpdated]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  return (
    <div className="p-6 bg-background text-text-primary">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold">{t('documentList.documents')}</h2>
        <Button asChild>
          <label>
            <Paperclip className="mr-2 h-4 w-4" />
            {t('documentList.uploadDocument')}
            <input type="file" className="hidden" onChange={handleFileChange} accept=".pdf" />
          </label>
        </Button>
      </div>
      <div className="bg-background-alt shadow rounded-lg">
        <div className="divide-y divide-border">
          {documents.map((doc) => {
            const title = doc.title || doc.metadata_?.title || doc.original_filename;
            const authors = doc.metadata_?.authors || doc.authors;
            const journal = doc.metadata_?.journal_or_source;
            const year = doc.metadata_?.publication_year;
            
            const formatAuthors = (authorsData: string | string[] | undefined): string => {
              if (!authorsData) return '';
              if (typeof authorsData === 'string') {
                try {
                  const parsed = JSON.parse(authorsData);
                  return Array.isArray(parsed) ? parsed.join(', ') : authorsData;
                } catch {
                  return authorsData;
                }
              }
              return Array.isArray(authorsData) ? authorsData.join(', ') : '';
            };
            
            const authorsFormatted = formatAuthors(authors);
            
            return (
              <div key={doc.id} className="group p-2 rounded-md transition-all duration-200 bg-background border border-border/50 hover:bg-muted/50 hover:border-border">
                <div className="flex items-start gap-2">
                  <div className="flex-shrink-0 mt-0.5">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <h4 className="font-medium text-sm leading-tight mb-1 line-clamp-2 text-foreground" title={title}>
                      {title}
                    </h4>
                    
                    {authorsFormatted && (
                      <p className="text-xs text-muted-foreground mb-1 line-clamp-1" title={authorsFormatted}>
                        {authorsFormatted}
                      </p>
                    )}
                    
                    <div className="space-y-0.5 mb-1">
                      {(journal || year) && (
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <BookOpen className="h-3 w-3 flex-shrink-0" />
                          <span className="truncate">
                            {journal && <span>{journal}</span>}
                            {journal && year && <span> • </span>}
                            {year && <span>{year}</span>}
                          </span>
                        </div>
                      )}
                      
                      {title !== doc.original_filename && (
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <FileText className="h-3 w-3 flex-shrink-0" />
                          <span className="truncate">{t('documentList.file', { filename: doc.original_filename })}</span>
                        </div>
                      )}
                    </div>
                    
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Calendar className="h-3 w-3" />
                        <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                      </div>
                      
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleViewDocument(doc);
                          }}
                          className="h-7 w-7 text-muted-foreground hover:text-primary"
                          title={t('documentList.viewMarkdown')}
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditDocument(doc);
                          }}
                          className="h-7 w-7 text-muted-foreground hover:text-primary"
                          title={t('documentList.editMetadata')}
                        >
                          <Edit className="h-3.5 w-3.5" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          onClick={() => onDelete(doc.id)} 
                          className="h-7 w-7 text-destructive hover:text-destructive/80"
                          title={t('documentList.deleteDocument')}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <DocumentMetadataEditModal
        document={selectedDocument}
        isOpen={editModalOpen}
        onClose={handleCloseModals}
        onSave={handleDocumentUpdated}
      />

      <DocumentViewModal
        document={selectedDocument}
        isOpen={viewModalOpen}
        onClose={handleCloseModals}
      />
    </div>
  );
};

export default DocumentList;
