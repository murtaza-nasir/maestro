import React, { useState, useEffect } from 'react';
import { getAllDocuments } from '../api';
import { EnhancedDocumentList } from './EnhancedDocumentList';
import { PaginationControls } from '../../../components/ui/PaginationControls';
import { DocumentFilters } from './DocumentFilters';
import { usePagination } from '../../../hooks/usePagination';
import type { PaginatedDocumentResponse } from '../types';

interface FilterOptions {
  search: string;
  author: string;
  year: string;
  journal: string;
}

interface DocumentBrowserProps {
  selectedGroupId?: string;
  onDocumentAdded?: () => void;
}

export const DocumentBrowser: React.FC<DocumentBrowserProps> = ({
  selectedGroupId,
  onDocumentAdded
}) => {
  const [paginatedResponse, setPaginatedResponse] = useState<PaginatedDocumentResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterOptions>({
    search: '',
    author: '',
    year: '',
    journal: ''
  });

  const pagination = usePagination();

  useEffect(() => {
    loadAllDocuments();
  }, [pagination.page, pagination.limit, filters]);

  const loadAllDocuments = async () => {
    try {
      setIsLoading(true);
      const response = await getAllDocuments({
        page: pagination.page,
        limit: pagination.limit,
        search: filters.search || undefined,
        author: filters.author || undefined,
        year: filters.year ? parseInt(filters.year) : undefined,
        journal: filters.journal || undefined
      });
      
      setPaginatedResponse(response);
      setError(null);
    } catch (err) {
      setError('Failed to load documents');
      console.error('Error loading documents:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDocumentDeleted = () => {
    loadAllDocuments();
    if (onDocumentAdded) {
      onDocumentAdded();
    }
  };

  if (isLoading && !paginatedResponse) {
    return (
      <div className="flex items-center justify-center p-8 bg-background">
        <div className="text-muted-foreground">Loading documents...</div>
      </div>
    );
  }

  const documents = paginatedResponse?.documents || [];
  const paginationInfo = paginatedResponse?.pagination;

  return (
    <div className="h-full flex flex-col bg-background">
      {error && (
        <div className="mb-4 bg-destructive/10 border border-destructive/20 rounded-md p-3">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Use the same DocumentFilters component as the main document viewer */}
      <DocumentFilters
        filters={filters}
        onFiltersChange={setFilters}
        groupId={undefined} // Browse mode shows all documents, not group-specific
        documentCount={paginationInfo?.total_count}
      />

      {/* Document List */}
      <div className="flex-1 min-h-0">
        <EnhancedDocumentList
          documents={documents}
          selectedGroupId={selectedGroupId}
          onDocumentDeleted={handleDocumentDeleted}
          onDocumentAdded={onDocumentAdded}
          showGroupActions={!!selectedGroupId}
          isGroupView={false}
          title={`All Documents${paginationInfo ? ` (${paginationInfo.total_count})` : ''}`}
        />
      </div>

      {/* Pagination Controls */}
      {paginationInfo && paginationInfo.total_pages > 1 && (
        <PaginationControls
          pagination={paginationInfo}
          onPageChange={pagination.handlePageChange}
          onLimitChange={pagination.handleLimitChange}
        />
      )}
    </div>
  );
};