import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  CheckSquare, 
  Square, 
  Trash2, 
  Plus, 
  Minus, 
  FileText, 
  Calendar, 
  BookOpen,
  Upload,
  Edit,
  Eye
} from 'lucide-react';
import type { Document } from '../types';
import { 
  bulkDeleteDocuments, 
  bulkAddDocumentsToGroup, 
  bulkRemoveDocumentsFromGroup
} from '../api';
import { useDocumentContext } from '../context/DocumentContext';
import { DeleteConfirmationModal } from '../../../components/ui/DeleteConfirmationModal';
import { useDocumentUploadManager } from '../context/DocumentUploadContext';
import { DocumentMetadataEditModal } from './DocumentMetadataEditModal';
import { DocumentViewModal } from './DocumentViewModal';

interface EnhancedDocumentListProps {
  documents: Document[];
  selectedGroupId?: string;
  onDocumentDeleted?: () => void;
  onDocumentAdded?: () => void;
  showGroupActions?: boolean;
  isGroupView?: boolean;
  title?: string;
}

export const EnhancedDocumentList: React.FC<EnhancedDocumentListProps> = ({
  documents,
  selectedGroupId,
  onDocumentDeleted,
  onDocumentAdded,
  showGroupActions = false,
  isGroupView = false,
}) => {
  const { t } = useTranslation();
  const { refreshGroups } = useDocumentContext();
  const { startUploads } = useDocumentUploadManager();
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set());
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);

  const filteredDocuments = documents;

  const handleSelectAll = () => {
    if (selectedDocuments.size === filteredDocuments.length) {
      setSelectedDocuments(new Set());
    } else {
      setSelectedDocuments(new Set(filteredDocuments.map(doc => doc.id)));
    }
  };

  const handleSelectDocument = (docId: string) => {
    const newSelected = new Set(selectedDocuments);
    if (newSelected.has(docId)) {
      newSelected.delete(docId);
    } else {
      newSelected.add(docId);
    }
    setSelectedDocuments(newSelected);
  };

  const handleDeleteClick = () => {
    if (selectedDocuments.size === 0) return;
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    try {
      setIsDeleting(true);
      await bulkDeleteDocuments(Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      onDocumentDeleted?.();
      refreshGroups();
      setError(null);
      setDeleteModalOpen(false);
    } catch (err) {
      setError(t('enhancedDocumentList.failedToDelete'));
      console.error('Bulk delete error:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteModalOpen(false);
    setIsDeleting(false);
  };

  const handleBulkAddToGroup = async () => {
    if (!selectedGroupId || selectedDocuments.size === 0) return;

    try {
      setIsProcessing(true);
      await bulkAddDocumentsToGroup(selectedGroupId, Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      onDocumentAdded?.();
      refreshGroups();
      setError(null);
    } catch (err) {
      setError(t('enhancedDocumentList.failedToAdd'));
      console.error('Bulk add error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleBulkRemoveFromGroup = async () => {
    if (!selectedGroupId || selectedDocuments.size === 0) return;

    const confirmMessage = t('enhancedDocumentList.removeConfirmation', { count: selectedDocuments.size });
    if (!confirm(confirmMessage)) return;

    try {
      setIsProcessing(true);
      await bulkRemoveDocumentsFromGroup(selectedGroupId, Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      onDocumentAdded?.();
      refreshGroups();
      setError(null);
    } catch (err) {
      setError(t('enhancedDocumentList.failedToRemove'));
      console.error('Bulk remove error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const formatAuthors = (authors: string | string[] | undefined): string => {
    if (!authors) return t('enhancedDocumentList.unknown');
    if (typeof authors === 'string') {
      try {
        const parsed = JSON.parse(authors);
        return Array.isArray(parsed) ? parsed.join(', ') : authors;
      } catch {
        return authors;
      }
    }
    return Array.isArray(authors) ? authors.join(', ') : t('enhancedDocumentList.unknown');
  };

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return '';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    
    const supportedTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword',
      'text/markdown',
      'text/x-markdown'
    ];
    
    const supportedExtensions = ['.pdf', '.docx', '.doc', '.md', '.markdown'];
    
    const allFiles = Array.from(e.dataTransfer.files);
    
    const files = allFiles.filter(file => {
      const hasValidType = supportedTypes.includes(file.type);
      const hasValidExtension = supportedExtensions.some(ext => 
        file.name.toLowerCase().endsWith(ext)
      );
      return hasValidType || hasValidExtension;
    });
    
    if (files.length > 0) {
      startUploads(files, selectedGroupId);
      onDocumentAdded?.();
    } else if (allFiles.length > 0) {
      console.error('All files were rejected by validation');
      setError(t('enhancedDocumentList.unsupportedFiles'));
    }
  }, [selectedGroupId, startUploads, onDocumentAdded, t]);

  const handleFilesSelected = useCallback((files: File[]) => {
    startUploads(files, selectedGroupId || null);
    onDocumentAdded?.();
  }, [selectedGroupId, startUploads, onDocumentAdded]);

  const handleEditDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setEditModalOpen(true);
  }, []);

  const handleViewDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setViewModalOpen(true);
  }, []);

  const handleDocumentUpdated = useCallback((_updatedDocument: Document) => {
    onDocumentAdded?.();
  }, [onDocumentAdded]);

  const handleCloseModals = useCallback(() => {
    setEditModalOpen(false);
    setViewModalOpen(false);
    setSelectedDocument(null);
  }, []);

  return (
    <div 
      className={`h-full bg-background flex flex-col relative ${isDragOver ? 'bg-primary/5' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragOver && (
        <div className="absolute inset-0 bg-primary/10 bg-opacity-75 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-background rounded-lg p-8 shadow-lg text-center border-2 border-primary border-dashed">
            <Upload className="h-16 w-16 text-primary mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-foreground mb-2">{t('enhancedDocumentList.dropDocuments')}</h3>
            <p className="text-muted-foreground">
              {t('enhancedDocumentList.supportedFiles')}
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="flex-shrink-0 mx-4 mt-3 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto min-h-0">
        {filteredDocuments.length > 0 && (
          <div className="flex-shrink-0 p-4 border-b border-border sticky top-0 z-10 bg-sidebar-background">
            <div className="flex items-center justify-between">
              <button
                onClick={handleSelectAll}
                className="flex items-center gap-2 text-sm text-foreground hover:text-primary"
              >
                {selectedDocuments.size === filteredDocuments.length ? (
                  <CheckSquare className="h-4 w-4" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                {t('enhancedDocumentList.selectAll', { count: filteredDocuments.length })}
              </button>

              {selectedDocuments.size > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-primary mr-2">
                    {t('enhancedDocumentList.selected', { count: selectedDocuments.size })}
                  </span>
                  {showGroupActions && isGroupView && selectedGroupId && (
                    <button
                      onClick={handleBulkRemoveFromGroup}
                      disabled={isProcessing}
                      className="flex items-center gap-1 px-3 py-1 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50"
                    >
                      <Minus className="h-3 w-3" />
                      {t('enhancedDocumentList.removeFromGroup')}
                    </button>
                  )}
                  {showGroupActions && !isGroupView && selectedGroupId && (
                    <button
                      onClick={handleBulkAddToGroup}
                      disabled={isProcessing}
                      className="flex items-center gap-1 px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50"
                    >
                      <Plus className="h-3 w-3" />
                      {t('enhancedDocumentList.addToGroup')}
                    </button>
                  )}
                  <button
                    onClick={handleDeleteClick}
                    disabled={isProcessing}
                    className="flex items-center gap-1 px-3 py-1 text-sm bg-destructive text-destructive-foreground rounded hover:bg-destructive/80 disabled:opacity-50"
                  >
                    <Trash2 className="h-3 w-3" />
                    {t('enhancedDocumentList.delete')}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {filteredDocuments.length === 0 ? (
          <div className="flex-1 flex items-center justify-center h-full">
            <div className="text-center">
              <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">
                {documents.length === 0 ? t('enhancedDocumentList.noDocumentsYet') : t('enhancedDocumentList.noMatchingDocuments')}
              </h3>
              <p className="text-muted-foreground">
                {documents.length === 0 
                  ? selectedGroupId 
                    ? t('enhancedDocumentList.dragAndDropOrBrowse')
                    : t('enhancedDocumentList.dragAndDrop')
                  : t('enhancedDocumentList.adjustFilters')
                }
              </p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredDocuments.map((doc) => {
            const isSelected = selectedDocuments.has(doc.id);
            const title = doc.title || doc.metadata_?.title || doc.original_filename;
            const authors = formatAuthors(doc.metadata_?.authors || doc.authors);
            const journal = doc.metadata_?.journal_or_source;
            const year = doc.metadata_?.publication_year;
            
            return (
              <div 
                key={doc.id} 
                className={`group p-2 rounded-md transition-all duration-200 ${
                  isSelected
                    ? 'bg-primary/5 border border-primary/20 shadow-sm'
                    : 'bg-background border border-border/50 hover:bg-muted/50 hover:border-border'
                }`}
              >
                <div className="flex items-start gap-2">
                  <button
                    onClick={() => handleSelectDocument(doc.id)}
                    className="flex-shrink-0 mt-0.5"
                  >
                    {isSelected ? (
                      <CheckSquare className="h-4 w-4 text-primary" />
                    ) : (
                      <Square className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    )}
                  </button>

                  <div className="flex-shrink-0 mt-0.5">
                    <FileText className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <h4 className={`font-medium text-sm leading-tight mb-1 line-clamp-2 ${
                      isSelected ? 'text-primary' : 'text-foreground'
                    }`} title={title}>
                      {title}
                    </h4>

                    {authors !== t('enhancedDocumentList.unknown') && (
                      <p className="text-xs text-muted-foreground mb-1 line-clamp-1" title={authors}>
                        {authors}
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
                          <span className="truncate">{t('enhancedDocumentList.file', { filename: doc.original_filename })}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                        </div>
                        {doc.file_size && (
                          <span>{formatFileSize(doc.file_size)}</span>
                        )}
                      </div>
                      
                      {(!doc.processing_status || doc.processing_status === 'completed' || doc.processing_status === 'failed') && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleViewDocument(doc);
                            }}
                            className="p-1 text-muted-foreground hover:text-primary rounded transition-colors"
                            title={t('enhancedDocumentList.viewDocument')}
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleEditDocument(doc);
                            }}
                            className="p-1 text-muted-foreground hover:text-primary rounded transition-colors"
                            title={t('enhancedDocumentList.editMetadata')}
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>

                    {doc.metadata_?.abstract && (
                      <div className="mt-2 text-xs text-muted-foreground">
                        <p className="line-clamp-2">{doc.metadata_.abstract}</p>
                      </div>
                    )}

                    {doc.processing_status && doc.processing_status !== 'completed' && (
                      <div className="mt-2">
                        <div className="flex items-center space-x-2">
                          <span className={`text-xs px-2 py-1 rounded-full ${
                            doc.processing_status === 'processing' 
                              ? 'bg-primary/10 text-primary'
                              : doc.processing_status === 'failed'
                              ? 'bg-destructive/10 text-destructive'
                              : 'bg-yellow-400/10 text-yellow-400'
                          }`}>
                            {doc.processing_status === 'processing' ? t('enhancedDocumentList.processing') :
                             doc.processing_status === 'failed' ? t('enhancedDocumentList.processingFailed') :
                             t('enhancedDocumentList.pendingProcessing')}
                          </span>
                          {doc.upload_progress !== undefined && doc.processing_status === 'processing' && (
                            <span className="text-xs text-muted-foreground">
                              {doc.upload_progress}%
                            </span>
                          )}
                        </div>
                        {doc.upload_progress !== undefined && doc.processing_status === 'processing' && (
                          <div className="mt-1 w-full bg-secondary rounded-full h-1">
                            <div
                              className="bg-primary h-1 rounded-full transition-all duration-300"
                              style={{ width: `${doc.upload_progress}%` }}
                            />
                          </div>
                        )}
                        {doc.processing_error && (
                          <p className="text-xs text-destructive mt-1">
                            {doc.processing_error}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
            </div>
        )}
      </div>

      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title={t('enhancedDocumentList.deleteDocuments')}
        description={t('enhancedDocumentList.deleteConfirmation', { count: selectedDocuments.size })}
        itemName={t('enhancedDocumentList.document', { count: selectedDocuments.size })}
        itemType="document"
        isLoading={isDeleting}
      />

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
