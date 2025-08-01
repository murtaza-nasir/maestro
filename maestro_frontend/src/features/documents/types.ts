export interface DocumentGroup {
  id: string;
  name: string;
  user_id: number;
  created_at: string;
  updated_at: string;
  description?: string;
  documents?: Document[];
}

export interface DocumentGroupWithCount extends DocumentGroup {
  document_count: number;
}

export interface Document {
  id: string;
  original_filename: string;
  user_id: number;
  created_at: string;
  title?: string;
  authors?: string | string[];
  processing_status?: 'pending' | 'processing' | 'completed' | 'failed';
  upload_progress?: number;
  processing_error?: string;
  file_size?: number;
  file_path?: string;
  metadata_?: {
    title?: string;
    authors?: string[];
    journal_or_source?: string;
    publication_year?: number;
    abstract?: string;
    keywords?: string[];
    doc_id?: string;
    chunk_id?: number;
    [key: string]: any;
  };
}

export interface SearchResult {
  doc_id: string;
  title: string;
  original_filename: string;
  authors: string;
  text_preview: string;
  score: number;
  chunk_id?: number;
}

export interface PaginationInfo {
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedDocumentResponse {
  documents: Document[];
  pagination: PaginationInfo;
  filters_applied: Record<string, any>;
}

export interface PaginationParams {
  page?: number;
  limit?: number;
  search?: string;
  author?: string;
  year?: number;
  journal?: string;
  status?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}
