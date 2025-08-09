import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Search,
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
import type { Document, PaginationInfo } from '../types';
import { 
  bulkDeleteDocuments, 
  bulkAddDocumentsToGroup, 
  bulkRemoveDocumentsFromGroup
} from '../api';
import { PaginationControls } from '../../../components/ui/PaginationControls';
import { useDocumentContext } from '../context/DocumentContext';
import { DeleteConfirmationModal } from '../../../components/ui/DeleteConfirmationModal';
import { DocumentUploadZone } from './DocumentUploadZone';
import { useDocumentUploadManager } from '../context/DocumentUploadContext';
import { DocumentMetadataEditModal } from './DocumentMetadataEditModal';
import { DocumentViewModal } from './DocumentViewModal';

interface EnhancedDocumentListProps {
  documents: Document[];
  selectedGroupId?: string;
  onDocumentDeleted?: () => void;
  onDocumentAdded?: () => void;
  showGroupActions?: boolean;
  isGroupView?: boolean; // true when viewing documents within a group, false when browsing to add to group
  title?: string;
  pagination?: PaginationInfo;
  onPageChange?: (page: number) => void;
  onLimitChange?: (limit: number) => void;
  searchValue?: string;
  onSearchChange?: (search: string) => void;
}

export const EnhancedDocumentList: React.FC<EnhancedDocumentListProps> = ({
  documents,
  selectedGroupId,
  onDocumentDeleted,
  onDocumentAdded,
  showGroupActions = false,
  isGroupView = false,
  pagination,
  onPageChange,
  onLimitChange,
  searchValue = '',
  onSearchChange,
}) => {
  const { refreshGroups } = useDocumentContext();
  const { startUploads } = useDocumentUploadManager();
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set());
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  
  // Modal state
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);

  // Extract unique filter options from documents
  const filterOptions = useMemo(() => {
    // console.log("EnhancedDocumentList: documents prop", documents);
    const authors = new Set<string>();
    const years = new Set<string>();
    const statuses = new Set<string>();

    documents.forEach(doc => {
      // Extract authors
      const docAuthors = doc.metadata_?.authors || doc.authors;
      if (docAuthors) {
        if (Array.isArray(docAuthors)) {
          docAuthors.forEach(author => authors.add(author));
        } else if (typeof docAuthors === 'string') {
          try {
            const parsed = JSON.parse(docAuthors);
            if (Array.isArray(parsed)) {
              parsed.forEach(author => authors.add(author));
            } else {
              authors.add(docAuthors);
            }
          } catch {
            authors.add(docAuthors);
          }
        }
      }

      // Extract years
      const year = doc.metadata_?.publication_year;
      if (year) {
        years.add(year.toString());
      }

      // Extract statuses
      if (doc.processing_status) {
        statuses.add(doc.processing_status);
      }
    });

    return {
      authors: Array.from(authors).sort(),
      years: Array.from(years).sort().reverse(),
      statuses: Array.from(statuses).sort()
    };
  }, [documents]);

  useEffect(() => {
    // console.log("EnhancedDocumentList: filterOptions", filterOptions);
  }, [filterOptions]);


  // Use documents directly since filtering is now handled server-side
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
      refreshGroups(); // Update group counts in sidebar and breadcrumb
      setError(null);
      setDeleteModalOpen(false);
    } catch (err) {
      setError('Failed to delete documents');
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
      refreshGroups(); // Update group counts in sidebar and breadcrumb
      setError(null);
    } catch (err) {
      setError('Failed to add documents to group');
      console.error('Bulk add error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleBulkRemoveFromGroup = async () => {
    if (!selectedGroupId || selectedDocuments.size === 0) return;

    const confirmMessage = `Remove ${selectedDocuments.size} document(s) from this group?`;
    if (!confirm(confirmMessage)) return;

    try {
      setIsProcessing(true);
      await bulkRemoveDocumentsFromGroup(selectedGroupId, Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      onDocumentAdded?.();
      refreshGroups(); // Update group counts in sidebar and breadcrumb
      setError(null);
    } catch (err) {
      setError('Failed to remove documents from group');
      console.error('Bulk remove error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const formatAuthors = (authors: string | string[] | undefined): string => {
    if (!authors) return 'Unknown';
    if (typeof authors === 'string') {
      try {
        const parsed = JSON.parse(authors);
        return Array.isArray(parsed) ? parsed.join(', ') : authors;
      } catch {
        return authors;
      }
    }
    return Array.isArray(authors) ? authors.join(', ') : 'Unknown';
  };

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return '';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Drag and drop handlers
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
    
    if (!selectedGroupId) {
      setError('Please select a document group first');
      return;
    }
    
    // Accept multiple file types: PDF, Word documents, and Markdown files
    const supportedTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
      'application/msword', // .doc
      'text/markdown', // .md
      'text/x-markdown' // alternative .md MIME type
    ];
    
    const supportedExtensions = ['.pdf', '.docx', '.doc', '.md', '.markdown'];
    
    const allFiles = Array.from(e.dataTransfer.files);
    console.log(`EnhancedDocumentList: Files dropped:`, allFiles.map(f => `${f.name} (type: ${f.type})`));
    
    const files = allFiles.filter(file => {
      const hasValidType = supportedTypes.includes(file.type);
      const hasValidExtension = supportedExtensions.some(ext => 
        file.name.toLowerCase().endsWith(ext)
      );
      
      const isValid = hasValidType || hasValidExtension;
      console.log(`File ${file.name}: type=${file.type}, extension valid=${hasValidExtension}, type valid=${hasValidType}, accepted=${isValid}`);
      
      // Accept file if either MIME type OR file extension matches
      return isValid;
    });
    
    console.log(`EnhancedDocumentList: ${files.length}/${allFiles.length} files passed validation`);
    
    if (files.length > 0) {
      startUploads(files, selectedGroupId);
      onDocumentAdded?.();
    } else if (allFiles.length > 0) {
      console.error('All files were rejected by validation');
      setError(`Unsupported file types. Supported: PDF, Word (docx/doc), Markdown (md/markdown)`);
    }
  }, [selectedGroupId, startUploads, onDocumentAdded]);

  const handleFilesSelected = useCallback((files: File[]) => {
    console.log(`handleFilesSelected called with ${files.length} files:`, files.map(f => f.name));
    console.log('selectedGroupId:', selectedGroupId);
    
    if (!selectedGroupId) {
      const errorMsg = 'Please select a document group first';
      console.error(errorMsg);
      setError(errorMsg);
      return;
    }
    
    console.log('Starting uploads...');
    startUploads(files, selectedGroupId);
    onDocumentAdded?.();
  }, [selectedGroupId, startUploads, onDocumentAdded]);

  // Modal handlers
  const handleEditDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setEditModalOpen(true);
  }, []);

  const handleViewDocument = useCallback((document: Document) => {
    setSelectedDocument(document);
    setViewModalOpen(true);
  }, []);

  const handleDocumentUpdated = useCallback((_updatedDocument: Document) => {
    // Refresh the documents list
    onDocumentAdded?.(); // This will trigger a refresh
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
      {/* Drag overlay */}
      {isDragOver && (
        <div className="absolute inset-0 bg-primary/10 bg-opacity-75 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-background rounded-lg p-8 shadow-lg text-center border-2 border-primary border-dashed">
            <Upload className="h-16 w-16 text-primary mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-foreground mb-2">Drop documents here</h3>
            <p className="text-muted-foreground">
              {selectedGroupId 
                ? 'Supports PDF, Word (docx/doc), and Markdown (md) files'
                : 'Select a document group first to upload files'
              }
            </p>
          </div>
        </div>
      )}
      {/* Search Bar - matching DocumentBrowser and sidebar styling exactly */}
      {onSearchChange && (
        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
            <input
              type="text"
              placeholder="Search by title, author, or filename..."
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
            />
          </div>
        </div>
      )}

      {/* Error Section */}
      {error && (
        <div className="flex-shrink-0 mx-4 mt-3 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Document List */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* Select All Header */}
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
                Select all {filteredDocuments.length} document{filteredDocuments.length !== 1 ? 's' : ''}
              </button>

              {/* Bulk Actions */}
              {selectedDocuments.size > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-primary mr-2">
                    {selectedDocuments.size} selected
                  </span>
                  {showGroupActions && isGroupView && selectedGroupId && (
                    <button
                      onClick={handleBulkRemoveFromGroup}
                      disabled={isProcessing}
                      className="flex items-center gap-1 px-3 py-1 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50"
                    >
                      <Minus className="h-3 w-3" />
                      Remove from Group
                    </button>
                  )}
                  {showGroupActions && !isGroupView && selectedGroupId && (
                    <button
                      onClick={handleBulkAddToGroup}
                      disabled={isProcessing}
                      className="flex items-center gap-1 px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50"
                    >
                      <Plus className="h-3 w-3" />
                      Add to Group
                    </button>
                  )}
                  <button
                    onClick={handleDeleteClick}
                    disabled={isProcessing}
                    className="flex items-center gap-1 px-3 py-1 text-sm bg-destructive text-destructive-foreground rounded hover:bg-destructive/80 disabled:opacity-50"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {filteredDocuments.length === 0 ? (
          <div className="flex-1 flex flex-col">
            {documents.length === 0 && selectedGroupId ? (
              // Show upload zone when no documents in group
              <div className="flex-1 p-6">
                <DocumentUploadZone
                  selectedGroupId={selectedGroupId}
                  onFilesSelected={handleFilesSelected}
                />
              </div>
            ) : (
              // Show empty state for filtered results or no group selected
              <div className="flex-1 flex items-center justify-center h-full">
                <div className="text-center">
                  <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-foreground mb-2">
                    {documents.length === 0 ? 'No documents yet' : 'No documents match your filters'}
                  </h3>
                  <p className="text-muted-foreground">
                    {documents.length === 0 
                      ? 'Upload PDF documents or browse the document library to get started.'
                      : 'Try adjusting your search terms or filters.'
                    }
                  </p>
                </div>
              </div>
            )}
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
                  {/* Selection Checkbox */}
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

                  {/* Document Icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    <FileText className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                  </div>

                  {/* Document Content */}
                  <div className="flex-1 min-w-0">
                    {/* Title */}
                    <h4 className={`font-medium text-sm leading-tight mb-1 line-clamp-2 ${
                      isSelected ? 'text-primary' : 'text-foreground'
                    }`} title={title}>
                      {title}
                    </h4>

                    {/* Authors subtitle */}
                    {authors !== 'Unknown' && (
                      <p className="text-xs text-muted-foreground mb-1 line-clamp-1" title={authors}>
                        {authors}
                      </p>
                    )}

                    {/* Metadata */}
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

                      {/* Filename if different from title */}
                      {title !== doc.original_filename && (
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <FileText className="h-3 w-3 flex-shrink-0" />
                          <span className="truncate">File: {doc.original_filename}</span>
                        </div>
                      )}
                    </div>

                    {/* Bottom Row: Date and File Size */}
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
                      
                      {/* Action buttons - only show for completed documents */}
                      {doc.processing_status === 'completed' && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleViewDocument(doc);
                            }}
                            className="p-1 text-muted-foreground hover:text-primary rounded transition-colors"
                            title="View document"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleEditDocument(doc);
                            }}
                            className="p-1 text-muted-foreground hover:text-primary rounded transition-colors"
                            title="Edit metadata"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Processing Status */}
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
                            {doc.processing_status === 'processing' ? 'Processing...' :
                             doc.processing_status === 'failed' ? 'Processing Failed' :
                             'Pending Processing'}
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

      {/* Pagination Controls */}
      {pagination && onPageChange && onLimitChange && documents.length > 0 && (
        <PaginationControls
          pagination={pagination}
          onPageChange={onPageChange}
          onLimitChange={onLimitChange}
        />
      )}

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Documents"
        description={`Are you sure you want to delete ${selectedDocuments.size} document${selectedDocuments.size !== 1 ? 's' : ''}? This action cannot be undone.`}
        itemName={selectedDocuments.size === 1 ? 'document' : `${selectedDocuments.size} documents`}
        itemType="document"
        isLoading={isDeleting}
      />

      {/* Document Metadata Edit Modal */}
      <DocumentMetadataEditModal
        document={selectedDocument}
        isOpen={editModalOpen}
        onClose={handleCloseModals}
        onSave={handleDocumentUpdated}
      />

      {/* Document View Modal */}
      <DocumentViewModal
        document={selectedDocument}
        isOpen={viewModalOpen}
        onClose={handleCloseModals}
      />
    </div>
  );
};
