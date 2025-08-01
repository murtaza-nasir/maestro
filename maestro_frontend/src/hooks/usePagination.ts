import { useState, useCallback } from 'react';
import type { PaginationParams } from '../features/documents/api';

interface UsePaginationProps {
  initialPage?: number;
  initialLimit?: number;
  onParamsChange?: (params: PaginationParams) => void;
}

export const usePagination = ({ 
  initialPage = 1, 
  initialLimit = 20,
  onParamsChange 
}: UsePaginationProps = {}) => {
  const [page, setPage] = useState(initialPage);
  const [limit, setLimit] = useState(initialLimit);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
    onParamsChange?.({ page: newPage, limit });
  }, [limit, onParamsChange]);

  const handleLimitChange = useCallback((newLimit: number) => {
    setLimit(newLimit);
    setPage(1); // Reset to first page when changing limit
    onParamsChange?.({ page: 1, limit: newLimit });
  }, [onParamsChange]);

  const reset = useCallback(() => {
    setPage(initialPage);
    setLimit(initialLimit);
    onParamsChange?.({ page: initialPage, limit: initialLimit });
  }, [initialPage, initialLimit, onParamsChange]);

  return {
    page,
    limit,
    handlePageChange,
    handleLimitChange,
    reset,
    params: { page, limit }
  };
};
