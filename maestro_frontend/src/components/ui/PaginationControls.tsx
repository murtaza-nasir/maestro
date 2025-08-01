import React from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import type { PaginationInfo } from '../../features/documents/api';

interface PaginationControlsProps {
  pagination: PaginationInfo;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  className?: string;
}

export const PaginationControls: React.FC<PaginationControlsProps> = ({
  pagination,
  onPageChange,
  onLimitChange,
  className = ''
}) => {
  const { page, total_pages, total_count, limit, has_previous, has_next } = pagination;

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= total_pages) {
      onPageChange(newPage);
    }
  };

  const getPageNumbers = () => {
    const pages = [];
    const maxVisiblePages = 5;
    
    if (total_pages <= maxVisiblePages) {
      for (let i = 1; i <= total_pages; i++) {
        pages.push(i);
      }
    } else {
      const start = Math.max(1, page - 2);
      const end = Math.min(total_pages, start + maxVisiblePages - 1);
      
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
    }
    
    return pages;
  };

  const startItem = (page - 1) * limit + 1;
  const endItem = Math.min(page * limit, total_count);

  return (
    <div className={`flex items-center justify-between bg-background px-4 py-3 border-t border-border ${className}`}>
      {/* Results info */}
      <div className="flex items-center gap-4">
        <div className="text-sm text-text-secondary">
          Showing <span className="font-medium text-text-primary">{startItem}</span> to{' '}
          <span className="font-medium text-text-primary">{endItem}</span> of{' '}
          <span className="font-medium text-text-primary">{total_count}</span> results
        </div>
        
        {/* Page size selector */}
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-secondary">Show:</label>
          <select
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
            className="border border-border rounded px-2 py-1 text-sm focus:ring-2 focus:ring-primary focus:border-transparent bg-background-alt text-text-primary"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
      </div>

      {/* Pagination controls */}
      <div className="flex items-center gap-1">
        {/* First page */}
        <button
          onClick={() => handlePageChange(1)}
          disabled={!has_previous}
          className="p-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          title="First page"
        >
          <ChevronsLeft className="h-4 w-4" />
        </button>

        {/* Previous page */}
        <button
          onClick={() => handlePageChange(page - 1)}
          disabled={!has_previous}
          className="p-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          title="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        {/* Page numbers */}
        <div className="flex items-center gap-1 mx-2">
          {getPageNumbers().map((pageNum) => (
            <button
              key={pageNum}
              onClick={() => handlePageChange(pageNum)}
              className={`px-3 py-1 text-sm rounded-md ${
                pageNum === page
                  ? 'bg-primary text-primary-foreground'
                  : 'text-text-secondary hover:bg-muted'
              }`}
            >
              {pageNum}
            </button>
          ))}
        </div>

        {/* Next page */}
        <button
          onClick={() => handlePageChange(page + 1)}
          disabled={!has_next}
          className="p-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          title="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        {/* Last page */}
        <button
          onClick={() => handlePageChange(total_pages)}
          disabled={!has_next}
          className="p-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          title="Last page"
        >
          <ChevronsRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
