import React, { useState, useEffect, useCallback } from 'react';
import { Library, FolderOpen, Upload, ArrowLeft, Search } from 'lucide-react';
import type { Document, DocumentGroup, DocumentGroupWithCount, PaginationInfo } from '../features/documents/types';
import { getAllDocuments, getGroupDocuments } from '../features/documents/api';
import { useDocumentContext } from '../features/documents/context/DocumentContext';
import { DocumentBrowser } from '../features/documents/components/DocumentBrowser';
import { EnhancedDocumentList } from '../features/documents/components/EnhancedDocumentList';
import { useDocumentUploadManager } from '../features/documents/context/DocumentUploadContext';
import { PaginationControls } from '../components/ui/PaginationControls';
import { uploadService } from '../features/documents/services/uploadService';
import { DocumentFilters } from '../features/documents/components/DocumentFilters';

interface FilterOptions {
  search: string;
  author: string;
  year: string;
  journal: string;
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
  const [filters, setFilters] = useState<FilterOptions>({
    search: '',
    author: '',
    year: '',
    journal: ''
  });
  const [isDragOver, setIsDragOver] = useState(false);

  const { startUploads } = useDocumentUploadManager();

  // Automatically switch to 'group' tab when a group is selected and reset pagination
  useEffect(() => {
    if (selectedGroup) {
      setActiveTab('group');
      // Reset pagination and filters when switching to a group
      setPagination(prev => ({ ...prev, page: 1 }));
      setFilters({
        search: '',
        author: '',
        year: '',
        journal: ''
      }); // Clear filters
    }
  }, [selectedGroup]);

  // Reset pagination and filters when switching back to all documents
  useEffect(() => {
    if (!selectedGroup) {
      setPagination(prev => ({ ...prev, page: 1 }));
      setFilters({
        search: '',
        author: '',
        year: '',
        journal: ''
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
    // console.log(`DocumentsPage: handleFilesSelected called with ${files.length} files:`, files.map(f => `${f.name} (${f.type})`));
    
    // If no group selected, upload to user's general documents (no group)
    const groupId = selectedGroup?.id || null;
    // console.log(`Starting uploads for group: ${groupId || 'no group (general documents)'}`);
    startUploads(files, groupId);
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
      // console.log('Document processing completed:', documentId);
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
    // console.log(`DocumentsPage: Files dropped:`, allFiles.map(f => `${f.name} (type: ${f.type})`));
    
    const files = allFiles.filter(file => {
      const hasValidType = supportedTypes.includes(file.type);
      const hasValidExtension = supportedExtensions.some(ext => 
        file.name.toLowerCase().endsWith(ext)
      );
      
      const isValid = hasValidType || hasValidExtension;
      // console.log(`File ${file.name}: type=${file.type}, extension valid=${hasValidExtension}, type valid=${hasValidType}, accepted=${isValid}`);
      
      // Accept file if either MIME type OR file extension matches
      return isValid;
    });
    
    // console.log(`DocumentsPage: ${files.length}/${allFiles.length} files passed validation`);
    
    if (files.length > 0) {
      handleFilesSelected(files);
    } else if (allFiles.length > 0) {
      console.error('All files were rejected by validation');
      setError(`Unsupported file types. Supported: PDF, Word (docx/doc), Markdown (md/markdown)`);
    }
  }, [handleFilesSelected]);


  const handleFiltersChange = useCallback((newFilters: FilterOptions) => {
    setFilters(newFilters);
    // Reset to first page when filters change
    setPagination(prev => ({ ...prev, page: 1 }));
  }, []);

  // Pagination handlers
  const handlePageChange = (newPage: number) => {
    setPagination(prev => ({ ...prev, page: newPage }));
  };

  const handleLimitChange = (newLimit: number) => {
    setPagination(prev => ({ ...prev, limit: newLimit, page: 1 })); // Reset to page 1 when changing limit
  };


  // Main document library view (when no group selected)
  if (!selectedGroup) {
    return (
      <div className="h-full flex flex-col">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
          <div className="flex items-center space-x-2">
            <Library className="h-5 w-5 text-primary" />
            <span className="text-lg font-semibold text-foreground">Document Library</span>
            <span className="text-muted-foreground">/</span>
            <span className="text-lg font-medium text-foreground">All Documents</span>
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
            
            {/* Document Filters */}
            <DocumentFilters
              filters={filters}
              onFiltersChange={handleFiltersChange}
              documentCount={pagination.total_count}
            />

            {/* Document List using EnhancedDocumentList component */}
            <div className="flex-1 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center p-8">
                  <div className="text-gray-500">Loading documents...</div>
                </div>
              ) : (
                <EnhancedDocumentList 
                  documents={documents}
                  selectedGroupId={undefined}
                  onDocumentAdded={handleDocumentAdded}
                  onDocumentDeleted={handleDocumentAdded}
                  showGroupActions={false}
                  isGroupView={false}
                />
              )}
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
          <div className="h-full bg-background flex flex-col">
            {/* Document Filters for Group View */}
            <DocumentFilters
              filters={filters}
              onFiltersChange={handleFiltersChange}
              groupId={selectedGroup.id}
              documentCount={pagination.total_count}
            />
            
            {/* Document List */}
            <div className="flex-1 overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center p-8">
                  <div className="text-gray-500">Loading documents...</div>
                </div>
              ) : (
                <EnhancedDocumentList 
                  documents={documents}
                  selectedGroupId={selectedGroup.id}
                  onDocumentAdded={handleDocumentAdded}
                  onDocumentDeleted={handleDocumentAdded}
                  showGroupActions={true}
                  isGroupView={true}
                />
              )}
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
