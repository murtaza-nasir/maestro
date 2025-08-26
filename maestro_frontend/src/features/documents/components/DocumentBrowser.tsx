import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Filter, X } from 'lucide-react';
import { getAllDocuments } from '../api';
import { EnhancedDocumentList } from './EnhancedDocumentList';
import { PaginationControls } from '../../../components/ui/PaginationControls';
import { usePagination } from '../../../hooks/usePagination';
import { useDocumentFilters } from '../../../hooks/useDocumentFilters';
import type { PaginatedDocumentResponse } from '../types';

interface DocumentBrowserProps {
  selectedGroupId?: string;
  onDocumentAdded?: () => void;
}

export const DocumentBrowser: React.FC<DocumentBrowserProps> = ({
  selectedGroupId,
  onDocumentAdded
}) => {
  const { t } = useTranslation();
  const [paginatedResponse, setPaginatedResponse] = useState<PaginatedDocumentResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const pagination = usePagination();
  const filters = useDocumentFilters();

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
      setError(t('documentBrowser.failedToLoad'));
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
        <div className="text-muted-foreground">{t('documentBrowser.loading')}</div>
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

      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
          <input
            type="text"
            placeholder={t('documentBrowser.searchPlaceholder')}
            value={filters.search}
            onChange={(e) => filters.updateSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
          />
        </div>
      </div>

      <div className="p-3 border-b border-border space-y-3">
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
            {t('documentBrowser.filters')}
            {filters.hasActiveFilters && <span className="ml-1 bg-primary text-primary-foreground rounded-full w-2 h-2"></span>}
          </button>

          {paginationInfo && (
            <div className="text-sm text-muted-foreground">
              {t('documentBrowser.showingDocuments', {
                from: ((paginationInfo.page - 1) * paginationInfo.limit) + 1,
                to: Math.min(paginationInfo.page * paginationInfo.limit, paginationInfo.total_count),
                total: paginationInfo.total_count
              })}
            </div>
          )}
        </div>

        {showFilters && (
          <div className="p-3 bg-secondary rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">{t('documentBrowser.author')}</label>
                <input
                  type="text"
                  placeholder={t('documentBrowser.authorPlaceholder')}
                  value={filters.author}
                  onChange={(e) => filters.updateAuthor(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">{t('documentBrowser.year')}</label>
                <input
                  type="number"
                  placeholder={t('documentBrowser.yearPlaceholder')}
                  value={filters.year || ''}
                  onChange={(e) => filters.updateYear(e.target.value ? parseInt(e.target.value) : undefined)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">{t('documentBrowser.journal')}</label>
                <input
                  type="text"
                  placeholder={t('documentBrowser.journalPlaceholder')}
                  value={filters.journal}
                  onChange={(e) => filters.updateJournal(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">{t('documentBrowser.status')}</label>
                <select
                  value={filters.status}
                  onChange={(e) => filters.updateStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent bg-background"
                >
                  <option value="">{t('documentBrowser.allStatuses')}</option>
                  <option value="completed">{t('documentBrowser.completed')}</option>
                  <option value="processing">{t('documentBrowser.processing')}</option>
                  <option value="failed">{t('documentBrowser.failed')}</option>
                  <option value="pending">{t('documentBrowser.pending')}</option>
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
                  {t('documentBrowser.clearFilters')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0">
        <EnhancedDocumentList
          documents={documents}
          selectedGroupId={selectedGroupId}
          onDocumentDeleted={handleDocumentDeleted}
          onDocumentAdded={onDocumentAdded}
          showGroupActions={!!selectedGroupId}
          isGroupView={false}
          title={`${t('documentBrowser.allDocuments')}${paginationInfo ? ` (${paginationInfo.total_count})` : ''}`}
        />
      </div>

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
