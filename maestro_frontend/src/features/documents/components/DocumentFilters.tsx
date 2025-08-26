import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Filter, X, ChevronDown, Calendar, User, BookOpen } from 'lucide-react';
import { getFilterOptions } from '../api';
import { useDebounce } from '../../../hooks/useDebounce';

interface FilterOptions {
  search: string;
  author: string;
  year: string;
  journal: string;
}

interface DocumentFiltersProps {
  filters: FilterOptions;
  onFiltersChange: (filters: FilterOptions) => void;
  groupId?: string;
  documentCount?: number;
}

export const DocumentFilters: React.FC<DocumentFiltersProps> = ({
  filters,
  onFiltersChange,
  groupId,
  documentCount = 0
}) => {
  const { t } = useTranslation();
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{
    authors: string[];
    years: number[];
    journals: string[];
  }>({ authors: [], years: [], journals: [] });
  
  const [localSearch, setLocalSearch] = useState(filters.search);
  const [dropdownOpen, setDropdownOpen] = useState<string | null>(null);
  const [searchTerms, setSearchTerms] = useState<{ [key: string]: string }>({ 
    author: '', 
    year: '', 
    journal: '' 
  });
  
  const debouncedSearch = useDebounce(localSearch, 500);
  
  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const options = await getFilterOptions(groupId);
        setFilterOptions(options);
      } catch (error) {
        console.error(t('documentFilters.failedToLoad'), error);
      }
    };
    loadFilterOptions();
  }, [groupId, t]);
  
  useEffect(() => {
    if (debouncedSearch !== filters.search) {
      onFiltersChange({ ...filters, search: debouncedSearch });
    }
  }, [debouncedSearch]);
  
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalSearch(e.target.value);
  };
  
  const handleFilterChange = (key: keyof FilterOptions, value: string) => {
    onFiltersChange({ ...filters, [key]: value });
    setDropdownOpen(null);
  };
  
  const clearFilter = (key: keyof FilterOptions) => {
    onFiltersChange({ ...filters, [key]: '' });
  };
  
  const clearAllFilters = () => {
    setLocalSearch('');
    onFiltersChange({
      search: '',
      author: '',
      year: '',
      journal: ''
    });
  };
  
  const hasActiveFilters = useMemo(() => {
    return filters.author || filters.year || filters.journal;
  }, [filters]);
  
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.author) count++;
    if (filters.year) count++;
    if (filters.journal) count++;
    return count;
  }, [filters]);
  
  const toggleDropdown = (dropdown: string) => {
    setDropdownOpen(dropdownOpen === dropdown ? null : dropdown);
    setSearchTerms(prev => ({ ...prev, [dropdown]: '' }));
  };
  
  const handleSearchTermChange = (field: string, value: string) => {
    setSearchTerms(prev => ({ ...prev, [field]: value }));
  };
  
  const getFilteredOptions = (field: string, options: any[]) => {
    const searchTerm = searchTerms[field]?.toLowerCase() || '';
    if (!searchTerm) return options;
    
    return options.filter(option => {
      const optionStr = option.toString().toLowerCase();
      return optionStr.includes(searchTerm);
    });
  };
  
  return (
    <div className="bg-background border-b border-border">
      <div className="p-4 pb-2 flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder={t('documentFilters.searchPlaceholder')}
            value={localSearch}
            onChange={handleSearchChange}
            className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent text-sm bg-background text-foreground placeholder:text-muted-foreground"
          />
          {localSearch && (
            <button
              onClick={() => setLocalSearch('')}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        
        <button
          onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
          className={`flex items-center gap-2 px-4 py-2 text-sm rounded-lg transition-colors border ${
            showAdvancedFilters || hasActiveFilters
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-muted text-foreground hover:bg-muted/80 border-border'
          }`}
        >
          <Filter className="h-4 w-4" />
          <span>{t('documentFilters.filters')}</span>
          {activeFilterCount > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-background text-foreground rounded-full">
              {activeFilterCount}
            </span>
          )}
          <ChevronDown className={`h-4 w-4 transition-transform ${
            showAdvancedFilters ? 'rotate-180' : ''
          }`} />
        </button>
      </div>
      
      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          {t('documentFilters.documentCount', { count: documentCount })}
        </div>
        
        {hasActiveFilters && (
          <div className="flex items-center gap-2">
            {filters.author && (
              <div className="flex items-center gap-1 px-2 py-1 bg-primary/10 text-primary rounded-md text-xs">
                <User className="h-3 w-3" />
                <span className="max-w-[150px] truncate">{filters.author}</span>
                <button
                  onClick={() => clearFilter('author')}
                  className="ml-1 hover:text-primary/80"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}
            {filters.year && (
              <div className="flex items-center gap-1 px-2 py-1 bg-primary/10 text-primary rounded-md text-xs">
                <Calendar className="h-3 w-3" />
                <span>{filters.year}</span>
                <button
                  onClick={() => clearFilter('year')}
                  className="ml-1 hover:text-primary/80"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}
            {filters.journal && (
              <div className="flex items-center gap-1 px-2 py-1 bg-primary/10 text-primary rounded-md text-xs">
                <BookOpen className="h-3 w-3" />
                <span className="max-w-[150px] truncate">{filters.journal}</span>
                <button
                  onClick={() => clearFilter('journal')}
                  className="ml-1 hover:text-primary/80"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}
            
            <button
              onClick={clearAllFilters}
              className="text-xs text-muted-foreground hover:text-foreground ml-2"
            >
              {t('documentFilters.clearAll')}
            </button>
          </div>
        )}
      </div>
      
      {showAdvancedFilters && (
        <div className="px-4 pb-4">
          <div className="p-4 bg-muted/30 rounded-lg border border-border">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="relative">
                <label className="block text-xs font-medium text-foreground mb-1.5">
                  {t('documentFilters.author')}
                </label>
                <div className="relative">
                  <button
                    onClick={() => toggleDropdown('author')}
                    className="w-full px-3 py-2 text-left border border-border rounded-md bg-background hover:bg-muted/50 focus:ring-2 focus:ring-primary focus:border-transparent flex items-center justify-between text-sm"
                  >
                    <span className={filters.author ? 'text-foreground' : 'text-muted-foreground'}>
                      {filters.author || t('documentFilters.selectAuthor')}
                    </span>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </button>
                  
                  {dropdownOpen === 'author' && (
                    <div className="absolute z-50 mt-1 w-full bg-background border border-border rounded-md shadow-lg max-h-60 overflow-hidden flex flex-col">
                      <div className="sticky top-0 bg-background border-b border-border p-2">
                        <input
                          type="text"
                          placeholder={t('documentFilters.typeToSearch')}
                          value={searchTerms.author}
                          onChange={(e) => handleSearchTermChange('author', e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full px-2 py-1 text-sm border border-border rounded bg-background focus:ring-1 focus:ring-primary focus:border-primary"
                          autoFocus
                        />
                      </div>
                      <div className="overflow-auto max-h-48">
                      <button
                        onClick={() => handleFilterChange('author', '')}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-muted/50 text-muted-foreground"
                      >
                        {t('documentFilters.allAuthors')}
                      </button>
                      {getFilteredOptions('author', filterOptions.authors).length === 0 ? (
                        <div className="px-3 py-2 text-sm text-muted-foreground italic">
                          {t('documentFilters.noMatchingAuthors')}
                        </div>
                      ) : (
                        getFilteredOptions('author', filterOptions.authors).map(author => (
                        <button
                          key={author}
                          onClick={() => handleFilterChange('author', author)}
                          className={`w-full px-3 py-2 text-left text-sm hover:bg-muted/50 ${
                            filters.author === author ? 'bg-primary/10 text-primary' : 'text-foreground'
                          }`}
                        >
                          {author}
                        </button>
                        ))
                      )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="relative">
                <label className="block text-xs font-medium text-foreground mb-1.5">
                  {t('documentFilters.year')}
                </label>
                <div className="relative">
                  <button
                    onClick={() => toggleDropdown('year')}
                    className="w-full px-3 py-2 text-left border border-border rounded-md bg-background hover:bg-muted/50 focus:ring-2 focus:ring-primary focus:border-transparent flex items-center justify-between text-sm"
                  >
                    <span className={filters.year ? 'text-foreground' : 'text-muted-foreground'}>
                      {filters.year || t('documentFilters.selectYear')}
                    </span>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </button>
                  
                  {dropdownOpen === 'year' && (
                    <div className="absolute z-50 mt-1 w-full bg-background border border-border rounded-md shadow-lg max-h-60 overflow-hidden flex flex-col">
                      <div className="sticky top-0 bg-background border-b border-border p-2">
                        <input
                          type="text"
                          placeholder={t('documentFilters.typeYear')}
                          value={searchTerms.year}
                          onChange={(e) => handleSearchTermChange('year', e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full px-2 py-1 text-sm border border-border rounded bg-background focus:ring-1 focus:ring-primary focus:border-primary"
                          autoFocus
                        />
                      </div>
                      <div className="overflow-auto max-h-48">
                      <button
                        onClick={() => handleFilterChange('year', '')}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-muted/50 text-muted-foreground"
                      >
                        {t('documentFilters.allYears')}
                      </button>
                      {getFilteredOptions('year', filterOptions.years).length === 0 ? (
                        <div className="px-3 py-2 text-sm text-muted-foreground italic">
                          {t('documentFilters.noMatchingYears')}
                        </div>
                      ) : (
                        getFilteredOptions('year', filterOptions.years).map(year => (
                        <button
                          key={year}
                          onClick={() => handleFilterChange('year', year.toString())}
                          className={`w-full px-3 py-2 text-left text-sm hover:bg-muted/50 ${
                            filters.year === year.toString() ? 'bg-primary/10 text-primary' : 'text-foreground'
                          }`}
                        >
                          {year}
                        </button>
                        ))
                      )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="relative">
                <label className="block text-xs font-medium text-foreground mb-1.5">
                  {t('documentFilters.journal')}
                </label>
                <div className="relative">
                  <button
                    onClick={() => toggleDropdown('journal')}
                    className="w-full px-3 py-2 text-left border border-border rounded-md bg-background hover:bg-muted/50 focus:ring-2 focus:ring-primary focus:border-transparent flex items-center justify-between text-sm"
                  >
                    <span className={filters.journal ? 'text-foreground' : 'text-muted-foreground'}>
                      {filters.journal || t('documentFilters.selectJournal')}
                    </span>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </button>
                  
                  {dropdownOpen === 'journal' && (
                    <div className="absolute z-50 mt-1 w-full bg-background border border-border rounded-md shadow-lg max-h-60 overflow-hidden flex flex-col">
                      <div className="sticky top-0 bg-background border-b border-border p-2">
                        <input
                          type="text"
                          placeholder={t('documentFilters.typeToSearch')}
                          value={searchTerms.journal}
                          onChange={(e) => handleSearchTermChange('journal', e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full px-2 py-1 text-sm border border-border rounded bg-background focus:ring-1 focus:ring-primary focus:border-primary"
                          autoFocus
                        />
                      </div>
                      <div className="overflow-auto max-h-48">
                      <button
                        onClick={() => handleFilterChange('journal', '')}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-muted/50 text-muted-foreground"
                      >
                        {t('documentFilters.allJournals')}
                      </button>
                      {getFilteredOptions('journal', filterOptions.journals).length === 0 ? (
                        <div className="px-3 py-2 text-sm text-muted-foreground italic">
                          {t('documentFilters.noMatchingJournals')}
                        </div>
                      ) : (
                        getFilteredOptions('journal', filterOptions.journals).map(journal => (
                        <button
                          key={journal}
                          onClick={() => handleFilterChange('journal', journal)}
                          className={`w-full px-3 py-2 text-left text-sm hover:bg-muted/50 ${
                            filters.journal === journal ? 'bg-primary/10 text-primary' : 'text-foreground'
                          }`}
                        >
                          {journal}
                        </button>
                        ))
                      )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};