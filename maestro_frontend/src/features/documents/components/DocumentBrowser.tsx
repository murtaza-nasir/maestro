import React, { useState, useEffect } from 'react';
import { Search, Filter, X } from 'lucide-react';
import { getAllDocuments } from '../api';
import { EnhancedDocumentList } from './EnhancedDocumentList';
import { PaginationControls } from '../../../components/ui/PaginationControls';
import { usePagination } from '../../../hooks/usePagination';
import { useDocumentFilters } from '../../../hooks/useDocumentFilters';
import type { PaginatedDocumentResponse } from '../types';
// import { useTheme } from '../../../contexts/ThemeContext';

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
  const [showFilters, setShowFilters] = useState(false);

  const pagination = usePagination();
  const filters = useDocumentFilters();
  // const { theme } = useTheme();

  useEffect(() => {
    loadAllDocuments();
  }, [pagination.page, pagination.limit, filters.filters]);

  const loadAllDocuments = async () => {
    try {
      setIsLoading(true);
      const response = await getAllDocuments({
        page: pagination.page,
        limit: pagination.limit,
        search: filters.search || undefined,
        author: filters.author || undefined,
        year: filters.year || undefined,
        journal: filters.journal || undefined,
        status: filters.status || undefined,
        sort_by: filters.sortBy,
        sort_order: filters.sortOrder
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

      {/* Search Bar - matching sidebar exactly */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search by title, author, or filename..."
            value={filters.search}
            onChange={(e) => filters.updateSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
          />
        </div>
      </div>

      {/* Filter Controls */}
      <div className="p-3 border-b border-border space-y-3">
        {/* Filter Toggle */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 px-3 py-1 text-sm rounded-md transition-colors ${
              showFilters || filters.hasActiveFilters
                ? 'bg-primary/10 text-primary'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            }`}
          >
            <Filter className="h-4 w-4" />
            Filters
            {filters.hasActiveFilters && <span className="ml-1 bg-primary text-primary-foreground rounded-full w-2 h-2"></span>}
          </button>

          {paginationInfo && (
            <div className="text-sm text-muted-foreground">
              Showing {((paginationInfo.page - 1) * paginationInfo.limit) + 1} to{' '}
              {Math.min(paginationInfo.page * paginationInfo.limit, paginationInfo.total_count)} of{' '}
              {paginationInfo.total_count} documents
            </div>
          )}
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="p-3 bg-secondary rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Author</label>
                <input
                  type="text"
                  placeholder="Filter by author..."
                  value={filters.author}
                  onChange={(e) => filters.updateAuthor(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Year</label>
                <input
                  type="number"
                  placeholder="Publication year..."
                  value={filters.year || ''}
                  onChange={(e) => filters.updateYear(e.target.value ? parseInt(e.target.value) : undefined)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Journal</label>
                <input
                  type="text"
                  placeholder="Filter by journal..."
                  value={filters.journal}
                  onChange={(e) => filters.updateJournal(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                <select
                  value={filters.status}
                  onChange={(e) => filters.updateStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                >
                  <option value="">All statuses</option>
                  <option value="completed">Completed</option>
                  <option value="processing">Processing</option>
                  <option value="failed">Failed</option>
                  <option value="pending">Pending</option>
                </select>
              </div>
            </div>
            
            {filters.hasActiveFilters && (
              <div className="mt-3 flex justify-end">
                <button
                  onClick={filters.clearFilters}
                  className="flex items-center gap-1 px-3 py-1 text-sm text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                  Clear filters
                </button>
              </div>
            )}
          </div>
        )}
      </div>

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
