import React, { useState, useEffect, useCallback } from 'react';
import { Library, FolderOpen, Search, Filter, CheckSquare, Square, Trash2, FileText, Calendar, BookOpen, X, Upload, FolderPlus, ArrowLeft } from 'lucide-react';
import type { Document, DocumentGroup, DocumentGroupWithCount, PaginationInfo } from '../features/documents/types';
import { getAllDocuments, getGroupDocuments, bulkDeleteDocuments, bulkAddDocumentsToGroup, getDocumentGroups, createDocumentGroup } from '../features/documents/api';
import { useDocumentContext } from '../features/documents/context/DocumentContext';
import { DocumentBrowser } from '../features/documents/components/DocumentBrowser';
import { EnhancedDocumentList } from '../features/documents/components/EnhancedDocumentList';
import { useDocumentUploadManager } from '../features/documents/context/DocumentUploadContext';
import { PaginationControls } from '../components/ui/PaginationControls';
import { uploadService } from '../features/documents/services/uploadService';
import { DeleteConfirmationModal } from '../components/ui/DeleteConfirmationModal';

interface FilterOptions {
  search: string;
  author: string;
  year: string;
  journal: string;
  status: string;
}

const DocumentsPage: React.FC = () => {
  const { selectedGroup, setSelectedGroup, refreshGroups, groupsRefreshKey } = useDocumentContext();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'group' | 'browse'>('group');
  
  // Pagination state
  const [pagination, setPagination] = useState<PaginationInfo>({
    total_count: 0,
    page: 1,
    limit: 20,
    total_pages: 0,
    has_next: false,
    has_previous: false
  });
  
  // Enhanced state for main document library
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<FilterOptions>({
    search: '',
    author: '',
    year: '',
    journal: '',
    status: ''
  });
  const [showFilters, setShowFilters] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [availableGroups, setAvailableGroups] = useState<DocumentGroup[]>([]);
  const [selectedGroupForBulk, setSelectedGroupForBulk] = useState<string>('');
  const [showCreateGroupModal, setShowCreateGroupModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const { startUploads } = useDocumentUploadManager();

  // Automatically switch to 'group' tab when a group is selected and reset pagination
  useEffect(() => {
    if (selectedGroup) {
      setActiveTab('group');
      // Reset pagination and filters when switching to a group
      setPagination(prev => ({ ...prev, page: 1 }));
      setSelectedDocuments(new Set()); // Clear selections
      setFilters({
        search: '',
        author: '',
        year: '',
        journal: '',
        status: ''
      }); // Clear filters
    }
  }, [selectedGroup]);

  // Reset pagination and filters when switching back to all documents
  useEffect(() => {
    if (!selectedGroup) {
      setPagination(prev => ({ ...prev, page: 1 }));
      setSelectedDocuments(new Set()); // Clear selections
      setFilters({
        search: '',
        author: '',
        year: '',
        journal: '',
        status: ''
      }); // Clear filters
    }
  }, [selectedGroup]);

  // Load documents based on context
  useEffect(() => {
    if (selectedGroup && activeTab === 'group') {
      fetchGroupDocuments(selectedGroup.id);
    } else if (!selectedGroup) {
      fetchAllDocuments();
    }
  }, [selectedGroup, activeTab, filters, pagination.page, pagination.limit]);

  // Load available groups for bulk operations
  useEffect(() => {
    const loadGroups = async () => {
      try {
        const groups = await getDocumentGroups();
        setAvailableGroups(groups);
      } catch (err) {
        console.error('Failed to load groups:', err);
      }
    };
    loadGroups();
  }, []);

  // Refresh available groups when groups are updated (renamed, deleted, etc.)
  useEffect(() => {
    const loadGroups = async () => {
      try {
        const groups = await getDocumentGroups();
        setAvailableGroups(groups);
      } catch (err) {
        console.error('Failed to refresh groups:', err);
      }
    };
    loadGroups();
  }, [groupsRefreshKey]);

  const fetchGroupDocuments = async (groupId: string) => {
    try {
      setLoading(true);
      const params: any = {
        limit: pagination.limit,
        page: pagination.page
      };
      
      // Add search filters for group documents (server-side filtering)
      if (filters.search) params.search = filters.search;
      if (filters.author) params.author = filters.author;
      if (filters.year) params.year = parseInt(filters.year);
      if (filters.journal) params.journal = filters.journal;
      if (filters.status) params.status = filters.status;
      
      const response = await getGroupDocuments(groupId, params);
      
      // Extract documents and pagination from response
      const docs = response.documents || [];
      setDocuments(docs);
      setPagination(response.pagination);
      setError(null);
    } catch (err) {
      setError('Failed to fetch documents.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAllDocuments = async () => {
    try {
      setLoading(true);
      const params: any = {
        limit: pagination.limit,
        page: pagination.page
      };
      
      if (filters.search) params.search = filters.search;
      if (filters.author) params.author = filters.author;
      if (filters.year) params.year = parseInt(filters.year);
      if (filters.journal) params.journal = filters.journal;
      if (filters.status) params.status = filters.status;
      
      const response = await getAllDocuments(params);
      
      // Extract documents and pagination from response
      const docs = response.documents || [];
      setDocuments(docs);
      setPagination(response.pagination);
      setError(null);
    } catch (err) {
      setError('Failed to fetch documents.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilesSelected = (files: File[]) => {
    console.log(`DocumentsPage: handleFilesSelected called with ${files.length} files:`, files.map(f => `${f.name} (${f.type})`));
    
    if (!selectedGroup) {
      const errorMsg = 'Please select a document group first';
      console.error(errorMsg);
      setError(errorMsg);
      return;
    }
    
    console.log(`Starting uploads for group: ${selectedGroup.id}`);
    startUploads(files, selectedGroup.id);
  };

  const handleDocumentAdded = () => {
    if (selectedGroup && activeTab === 'group') {
      fetchGroupDocuments(selectedGroup.id);
    } else if (!selectedGroup) {
      fetchAllDocuments();
    }
  };

  // Register for document processing completion notifications
  useEffect(() => {
    const unsubscribe = uploadService.onDocumentProcessingComplete((documentId) => {
      console.log('Document processing completed:', documentId);
      // Refresh the document list and groups when processing completes
      handleDocumentAdded();
      refreshGroups();
    });

    return unsubscribe;
  }, [handleDocumentAdded, refreshGroups]);

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
    console.log(`DocumentsPage: Files dropped:`, allFiles.map(f => `${f.name} (type: ${f.type})`));
    
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
    
    console.log(`DocumentsPage: ${files.length}/${allFiles.length} files passed validation`);
    
    if (files.length > 0) {
      handleFilesSelected(files);
    } else if (allFiles.length > 0) {
      console.error('All files were rejected by validation');
      setError(`Unsupported file types. Supported: PDF, Word (docx/doc), Markdown (md/markdown)`);
    }
  }, [handleFilesSelected]);

  // Document selection handlers
  const handleSelectAll = () => {
    if (selectedDocuments.size === documents.length) {
      setSelectedDocuments(new Set());
    } else {
      setSelectedDocuments(new Set(documents.map(doc => doc.id)));
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

  // Bulk operations
  const handleDeleteClick = () => {
    if (selectedDocuments.size === 0) return;
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    try {
      setIsDeleting(true);
      await bulkDeleteDocuments(Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      handleDocumentAdded();
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
    if (!selectedGroupForBulk || selectedDocuments.size === 0) return;

    try {
      setIsProcessing(true);
      await bulkAddDocumentsToGroup(selectedGroupForBulk, Array.from(selectedDocuments));
      setSelectedDocuments(new Set());
      setSelectedGroupForBulk('');
      handleDocumentAdded();
      refreshGroups(); // Update group counts in sidebar and breadcrumb
      setError(null);
    } catch (err) {
      setError('Failed to add documents to group');
      console.error('Bulk add error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCreateNewGroup = async () => {
    if (!newGroupName.trim() || selectedDocuments.size === 0) return;

    try {
      setIsProcessing(true);
      // Create the new group
      const newGroup = await createDocumentGroup(newGroupName.trim());
      
      // Add selected documents to the new group
      await bulkAddDocumentsToGroup(newGroup.id, Array.from(selectedDocuments));
      
      // Update available groups list
      const groups = await getDocumentGroups();
      setAvailableGroups(groups);
      
      // Refresh the sidebar groups list
      refreshGroups();
      
      // Clear selections and close modal
      setSelectedDocuments(new Set());
      setNewGroupName('');
      setShowCreateGroupModal(false);
      handleDocumentAdded();
      setError(null);
    } catch (err) {
      setError('Failed to create group and add documents');
      console.error('Create group error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  // Utility functions
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

  const clearFilters = () => {
    setFilters({
      search: '',
      author: '',
      year: '',
      journal: '',
      status: ''
    });
  };

  const hasActiveFilters = Object.values(filters).some(filter => filter !== '');

  // Pagination handlers
  const handlePageChange = (newPage: number) => {
    setPagination(prev => ({ ...prev, page: newPage }));
    setSelectedDocuments(new Set()); // Clear selections when changing pages
  };

  const handleLimitChange = (newLimit: number) => {
    setPagination(prev => ({ ...prev, limit: newLimit, page: 1 })); // Reset to page 1 when changing limit
    setSelectedDocuments(new Set()); // Clear selections when changing limit
  };

  // Extract unique filter options from documents
  const filterOptions = React.useMemo(() => {
    const authors = new Set<string>();
    const years = new Set<string>();
    const journals = new Set<string>();
    const statuses = new Set<string>();

    documents.forEach(doc => {
      // Extract authors
      const docAuthors = doc.metadata_?.authors;
      if (docAuthors && Array.isArray(docAuthors)) {
        docAuthors.forEach(author => authors.add(author));
      }

      // Extract years
      const year = doc.metadata_?.publication_year;
      if (year) {
        years.add(year.toString());
      }

      // Extract journals
      const journal = doc.metadata_?.journal_or_source;
      if (journal) {
        journals.add(journal);
      }

      // Extract statuses
      if (doc.processing_status) {
        statuses.add(doc.processing_status);
      }
    });

    return {
      authors: Array.from(authors).sort(),
      years: Array.from(years).sort().reverse(),
      journals: Array.from(journals).sort(),
      statuses: Array.from(statuses).sort()
    };
  }, [documents]);

  // Main document library view (when no group selected)
  if (!selectedGroup) {
    return (
      <div 
        className={`h-full flex flex-col ${isDragOver ? 'bg-blue-50' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drag overlay */}
        {isDragOver && (
          <div className="absolute inset-0 bg-blue-100 bg-opacity-75 flex items-center justify-center z-50 pointer-events-none">
            <div className="bg-white rounded-lg p-8 shadow-lg text-center">
              <Upload className="h-16 w-16 text-blue-500 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-gray-900 mb-2">Drop documents here</h3>
              <p className="text-gray-600">Supports PDF, Word (docx/doc), and Markdown (md) files</p>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="px-6 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <Library className="h-5 w-5 text-primary" />
              <span className="text-lg font-semibold text-foreground">Document Library</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-lg font-medium text-foreground">All Documents ({pagination.total_count})</span>
              {selectedDocuments.size > 0 && (
                <>
                  <span className="text-gray-400">•</span>
                  <span className="text-sm text-blue-600">{selectedDocuments.size} selected</span>
                </>
              )}
            </div>
            
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-1 px-3 py-1 text-sm rounded-md transition-colors ${
                showFilters || hasActiveFilters
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              <Filter className="h-4 w-4" />
              Filters
              {hasActiveFilters && <span className="ml-1 bg-blue-500 text-white rounded-full w-2 h-2"></span>}
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <div className="h-full bg-background flex flex-col">
            {/* Error Display */}
            {error && (
              <div className="mx-3 mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
                <p className="text-sm text-red-600">{error}</p>
                <button
                  onClick={() => setError(null)}
                  className="mt-1 text-xs text-red-500 hover:text-red-700 underline"
                >
                  Dismiss
                </button>
              </div>
            )}
            
            {/* Search Bar */}
            <div className="p-3 border-b border-border">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
                <input
                  type="text"
                  placeholder="Search by title, author, or filename..."
                  value={filters.search}
                  onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
                  className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
                />
              </div>
            </div>

            {/* Advanced Filters */}
            {showFilters && (
              <div className="p-4 bg-secondary rounded-lg mx-3 mb-3">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Author</label>
                    <select
                      value={filters.author}
                      onChange={(e) => setFilters(prev => ({ ...prev, author: e.target.value }))}
                      className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                    >
                      <option value="">All authors</option>
                      {filterOptions.authors.map(author => (
                        <option key={author} value={author}>{author}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Year</label>
                    <select
                      value={filters.year}
                      onChange={(e) => setFilters(prev => ({ ...prev, year: e.target.value }))}
                      className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                    >
                      <option value="">All years</option>
                      {filterOptions.years.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Journal</label>
                    <select
                      value={filters.journal}
                      onChange={(e) => setFilters(prev => ({ ...prev, journal: e.target.value }))}
                      className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                    >
                      <option value="">All journals</option>
                      {filterOptions.journals.map(journal => (
                        <option key={journal} value={journal}>{journal}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                    <select
                      value={filters.status}
                      onChange={(e) => setFilters(prev => ({ ...prev, status: e.target.value }))}
                      className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                    >
                      <option value="">All statuses</option>
                      {filterOptions.statuses.map(status => (
                        <option key={status} value={status}>{status}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                {hasActiveFilters && (
                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={clearFilters}
                      className="flex items-center gap-1 px-3 py-1 text-sm text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                      Clear filters
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Document List */}
            <div className="flex-1 overflow-y-auto min-h-0">
              {/* Select All Header */}
              {documents.length > 0 && (
                <div className="flex-shrink-0 p-4 border-b border-border sticky top-0 z-10 bg-sidebar-background">
                  <div className="flex items-center justify-between">
                    <button
                      onClick={handleSelectAll}
                      className="flex items-center gap-2 text-sm text-foreground hover:text-primary"
                    >
                      {selectedDocuments.size === documents.length ? (
                        <CheckSquare className="h-4 w-4" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                      Select all {documents.length} document{documents.length !== 1 ? 's' : ''}
                    </button>

                    {/* Bulk Actions */}
                    {selectedDocuments.size > 0 && (
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-primary mr-2">
                          {selectedDocuments.size} selected
                        </span>
                        <select
                          value={selectedGroupForBulk}
                          onChange={(e) => setSelectedGroupForBulk(e.target.value)}
                          className="px-2 py-1 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                          <option value="">Select group...</option>
                          {availableGroups.map(group => (
                            <option key={group.id} value={group.id}>{group.name}</option>
                          ))}
                        </select>
                        <button
                          onClick={handleBulkAddToGroup}
                          disabled={isProcessing || !selectedGroupForBulk}
                          className="flex items-center gap-1 px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50"
                        >
                          <FolderPlus className="h-3 w-3" />
                          Add to Group
                        </button>
                        <button
                          onClick={() => setShowCreateGroupModal(true)}
                          disabled={isProcessing}
                          className="flex items-center gap-1 px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                        >
                          <FolderPlus className="h-3 w-3" />
                          Create New Group
                        </button>
                        <button
                          onClick={handleDeleteClick}
                          disabled={isProcessing}
                          className="flex items-center gap-1 px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50"
                        >
                          <Trash2 className="h-3 w-3" />
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Document Content */}
              <div>
                {loading ? (
                  <div className="flex items-center justify-center p-8">
                    <div className="text-gray-500">Loading documents...</div>
                  </div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-12">
                    <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 mb-2">No documents found</h3>
                    <p className="text-gray-600">
                      {hasActiveFilters 
                        ? 'Try adjusting your search terms or filters.'
                        : 'Upload PDF documents to get started.'
                      }
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-border">
                    {documents.map((doc) => {
                      const isSelected = selectedDocuments.has(doc.id);
                      const title = doc.title || doc.metadata_?.title || doc.original_filename;
                      const authors = formatAuthors(doc.metadata_?.authors);
                      const journal = doc.metadata_?.journal_or_source;
                      const year = doc.metadata_?.publication_year;
                      const abstract = doc.metadata_?.abstract;
                      
                      return (
                        <div 
                          key={doc.id} 
                          className={`p-2 rounded-md transition-all duration-200 ${
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
                              </div>

                              {/* Abstract preview */}
                              {abstract && (
                                <div className="mt-2 text-xs text-muted-foreground">
                                  <p className="line-clamp-2">{abstract}</p>
                                </div>
                              )}

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
            </div>

            {/* Pagination Controls */}
            {documents.length > 0 && pagination.total_pages > 1 && (
              <PaginationControls
                pagination={pagination}
                onPageChange={handlePageChange}
                onLimitChange={handleLimitChange}
              />
            )}
          </div>
        </div>

        {/* Create New Group Modal */}
        {showCreateGroupModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Create New Group</h3>
              <p className="text-sm text-gray-600 mb-4">
                Create a new document group and add {selectedDocuments.size} selected document{selectedDocuments.size !== 1 ? 's' : ''} to it.
              </p>
              
              <div className="mb-4">
                <label htmlFor="groupName" className="block text-sm font-medium text-gray-700 mb-2">
                  Group Name
                </label>
                <input
                  id="groupName"
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="Enter group name..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newGroupName.trim()) {
                      handleCreateNewGroup();
                    } else if (e.key === 'Escape') {
                      setShowCreateGroupModal(false);
                      setNewGroupName('');
                    }
                  }}
                  autoFocus
                />
              </div>

              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowCreateGroupModal(false);
                    setNewGroupName('');
                  }}
                  disabled={isProcessing}
                  className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateNewGroup}
                  disabled={isProcessing || !newGroupName.trim()}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                >
                  {isProcessing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Creating...
                    </>
                  ) : (
                    <>
                      <FolderPlus className="h-4 w-4" />
                      Create Group
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
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
          variant={selectedDocuments.size > 1 ? 'bulk' : 'single'}
          count={selectedDocuments.size}
          isLoading={isDeleting}
        />
      </div>
    );
  }

  // Group view (when a group is selected)
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setSelectedGroup(null)}
              className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Library
            </button>
            <span className="text-muted-foreground">/</span>
            <FolderOpen className="h-5 w-5 text-primary" />
            <span className="text-lg font-medium text-foreground">{selectedGroup.name}</span>
            <span className="text-sm text-muted-foreground">({(selectedGroup as DocumentGroupWithCount).document_count || 0} documents)</span>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="flex bg-muted/60 backdrop-blur-sm rounded-lg p-0.5 border border-border/50">
              <button
                onClick={() => setActiveTab('group')}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-all duration-200 flex items-center ${
                  activeTab === 'group'
                    ? 'bg-background text-foreground shadow-sm border border-border/50'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                }`}
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                <span>Documents</span>
              </button>
              <button
                onClick={() => setActiveTab('browse')}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-all duration-200 flex items-center ${
                  activeTab === 'browse'
                    ? 'bg-background text-foreground shadow-sm border border-border/50'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                }`}
              >
                <Search className="h-4 w-4 mr-2" />
                <span>Browse & Add</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'group' ? (
          <EnhancedDocumentList 
            documents={documents}
            selectedGroupId={selectedGroup.id}
            onDocumentAdded={handleDocumentAdded}
            onDocumentDeleted={handleDocumentAdded}
            showGroupActions={true}
            isGroupView={true}
            pagination={pagination}
            onPageChange={handlePageChange}
            onLimitChange={handleLimitChange}
            searchValue={filters.search}
            onSearchChange={(search) => setFilters(prev => ({ ...prev, search }))}
          />
        ) : (
          <DocumentBrowser 
            selectedGroupId={selectedGroup.id}
            onDocumentAdded={handleDocumentAdded}
          />
        )}
      </div>
    </div>
  );
};

export default DocumentsPage;
