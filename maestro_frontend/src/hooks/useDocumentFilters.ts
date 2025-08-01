import { useState, useCallback, useMemo } from 'react';
import type { PaginationParams } from '../features/documents/api';

interface UseDocumentFiltersProps {
  onFiltersChange?: (filters: PaginationParams) => void;
}

export const useDocumentFilters = ({ onFiltersChange }: UseDocumentFiltersProps = {}) => {
  const [search, setSearch] = useState('');
  const [author, setAuthor] = useState('');
  const [year, setYear] = useState<number | undefined>();
  const [journal, setJournal] = useState('');
  const [status, setStatus] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const filters = useMemo(() => ({
    search: search || undefined,
    author: author || undefined,
    year: year || undefined,
    journal: journal || undefined,
    status: status || undefined,
    sort_by: sortBy,
    sort_order: sortOrder
  }), [search, author, year, journal, status, sortBy, sortOrder]);

  const updateSearch = useCallback((value: string) => {
    setSearch(value);
    const newFilters = { ...filters, search: value || undefined };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const updateAuthor = useCallback((value: string) => {
    setAuthor(value);
    const newFilters = { ...filters, author: value || undefined };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const updateYear = useCallback((value: number | undefined) => {
    setYear(value);
    const newFilters = { ...filters, year: value };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const updateJournal = useCallback((value: string) => {
    setJournal(value);
    const newFilters = { ...filters, journal: value || undefined };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const updateStatus = useCallback((value: string) => {
    setStatus(value);
    const newFilters = { ...filters, status: value || undefined };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const updateSort = useCallback((field: string, order: 'asc' | 'desc') => {
    setSortBy(field);
    setSortOrder(order);
    const newFilters = { ...filters, sort_by: field, sort_order: order };
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  const clearFilters = useCallback(() => {
    setSearch('');
    setAuthor('');
    setYear(undefined);
    setJournal('');
    setStatus('');
    setSortBy('created_at');
    setSortOrder('desc');
    onFiltersChange?.({
      sort_by: 'created_at',
      sort_order: 'desc'
    });
  }, [onFiltersChange]);

  const hasActiveFilters = useMemo(() => {
    return !!(search || author || year || journal || status);
  }, [search, author, year, journal, status]);

  return {
    filters,
    search,
    author,
    year,
    journal,
    status,
    sortBy,
    sortOrder,
    updateSearch,
    updateAuthor,
    updateYear,
    updateJournal,
    updateStatus,
    updateSort,
    clearFilters,
    hasActiveFilters
  };
};
