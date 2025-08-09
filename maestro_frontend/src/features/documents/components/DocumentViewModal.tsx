import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { 
  FileText, 
  Calendar, 
  Users, 
  BookOpen, 
  Tags,
  Loader2,
  Download
} from 'lucide-react';
import type { Document } from '../types';
import type { DocumentViewResponse } from '../api';
import { getDocumentContent } from '../api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

interface DocumentViewModalProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

export const DocumentViewModal: React.FC<DocumentViewModalProps> = ({
  document: documentProp,
  isOpen,
  onClose,
}) => {
  const [documentContent, setDocumentContent] = useState<DocumentViewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && documentProp) {
      loadDocumentContent();
    }
  }, [isOpen, documentProp]);

  const loadDocumentContent = async () => {
    if (!documentProp) return;

    setIsLoading(true);
    setError(null);

    try {
      const content = await getDocumentContent(documentProp.id);
      setDocumentContent(content);
    } catch (err: any) {
      console.error('Error loading document content:', err);
      setError(err.response?.data?.detail || 'Failed to load document content');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setDocumentContent(null);
    setError(null);
    onClose();
  };

  if (!documentProp) return null;

  const metadata = documentProp.metadata_ || {};
  
  // Parse authors
  let authorsArray: string[] = [];
  if (metadata.authors) {
    if (Array.isArray(metadata.authors)) {
      authorsArray = metadata.authors;
    } else if (typeof metadata.authors === 'string') {
      try {
        const parsed = JSON.parse(metadata.authors);
        authorsArray = Array.isArray(parsed) ? parsed : [metadata.authors];
      } catch {
        authorsArray = [metadata.authors];
      }
    }
  }

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'Unknown size';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-7xl max-h-[95vh] p-0 flex flex-col">
        <DialogHeader className="px-4 pt-4 pb-3 border-b">
          <DialogTitle className="flex items-center space-x-2">
            <FileText className="h-5 w-5 text-blue-600" />
            <span className="text-base font-semibold">
              {documentContent?.title || documentProp.title || documentProp.original_filename}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-hidden p-4 flex flex-col">
          {isLoading ? (
            <div className="flex items-center justify-center flex-1">
              <div className="text-center">
                <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-blue-600" />
                <p className="text-gray-600 text-lg">Loading document content...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center flex-1">
              <div className="text-center max-w-md">
                <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                  <p className="text-red-700 mb-4">{error}</p>
                  <Button 
                    variant="outline" 
                    size="default"
                    onClick={loadDocumentContent}
                  >
                    Retry Loading
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 flex-1 overflow-hidden">
              {/* Metadata Sidebar */}
              <div className="lg:col-span-1 bg-muted/30 rounded-lg p-4 space-y-3 overflow-y-auto">
                <h3 className="text-base font-semibold text-foreground mb-2 border-b border-border pb-1">Document Information</h3>
                
                <div className="space-y-3">
                  <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                    <label className="text-xs font-semibold text-foreground block mb-1">Original Filename</label>
                    <p className="text-xs text-muted-foreground break-words">{documentProp.original_filename}</p>
                  </div>

                  {authorsArray.length > 0 && (
                    <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                      <label className="text-xs font-semibold text-foreground flex items-center mb-2">
                        <Users className="h-3 w-3 mr-1 text-muted-foreground" />
                        Authors
                      </label>
                      <div className="flex flex-wrap gap-1">
                        {authorsArray.map((author, index) => (
                          <Badge key={index} variant="secondary" className="text-xs px-2 py-0.5">
                            {author}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {metadata.journal_or_source && (
                    <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                      <label className="text-xs font-semibold text-foreground flex items-center mb-1">
                        <BookOpen className="h-3 w-3 mr-1 text-muted-foreground" />
                        Journal/Source
                      </label>
                      <p className="text-xs text-muted-foreground">{metadata.journal_or_source}</p>
                    </div>
                  )}

                  {metadata.publication_year && (
                    <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                      <label className="text-xs font-semibold text-foreground flex items-center mb-1">
                        <Calendar className="h-3 w-3 mr-1 text-muted-foreground" />
                        Publication Year
                      </label>
                      <p className="text-xs text-muted-foreground">{metadata.publication_year}</p>
                    </div>
                  )}

                  {metadata.keywords && metadata.keywords.length > 0 && (
                    <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                      <label className="text-xs font-semibold text-foreground flex items-center mb-2">
                        <Tags className="h-3 w-3 mr-1 text-muted-foreground" />
                        Keywords
                      </label>
                      <div className="flex flex-wrap gap-1">
                        {metadata.keywords.map((keyword: string, index: number) => (
                          <Badge key={index} variant="outline" className="text-xs px-2 py-0.5">
                            {keyword}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                    <label className="text-xs font-semibold text-foreground block mb-1">File Size</label>
                    <p className="text-xs text-muted-foreground">{formatFileSize(documentProp.file_size)}</p>
                  </div>

                  <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                    <label className="text-xs font-semibold text-foreground block mb-1">Added</label>
                    <p className="text-xs text-muted-foreground">{formatDate(documentProp.created_at)}</p>
                  </div>

                  {documentProp.processing_status && (
                    <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                      <label className="text-xs font-semibold text-foreground block mb-1">Status</label>
                      <Badge 
                        variant={documentProp.processing_status === 'completed' ? 'default' : 'secondary'}
                        className="text-xs px-2 py-0.5"
                      >
                        {documentProp.processing_status}
                      </Badge>
                    </div>
                  )}
                </div>

                {metadata.abstract && (
                  <div className="bg-background rounded-lg p-3 border border-border shadow-sm">
                    <label className="text-xs font-semibold text-foreground mb-2 block">Abstract</label>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {metadata.abstract}
                    </p>
                  </div>
                )}
              </div>

              {/* Content Area */}
              <div className="lg:col-span-3 flex flex-col min-h-0">
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
                  <h3 className="text-base font-semibold text-foreground">Document Content</h3>
                  {documentContent?.content && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex items-center gap-2"
                      onClick={() => {
                        const blob = new Blob([documentContent.content], { type: 'text/markdown' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `${documentProp.original_filename.replace('.pdf', '')}.md`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <Download className="h-3 w-3" />
                      Download Markdown
                    </Button>
                  )}
                </div>

                <div className="flex-1 border border-border rounded-lg bg-background overflow-y-auto">
                  <div className="p-4">
                  {documentContent?.content ? (
                    <div className="prose prose-base max-w-none prose-headings:text-foreground prose-p:text-foreground prose-a:text-primary prose-strong:text-foreground prose-code:text-foreground prose-pre:bg-muted prose-blockquote:border-l-primary">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw]}
                        components={{
                          // Custom link component to open external links in new tab
                          a: ({ ...props }) => (
                              <a 
                                {...props} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-primary hover:text-primary/80 underline"
                              />
                            ),
                            // Custom table styling
                            table: ({ ...props }) => (
                              <div className="overflow-x-auto my-4">
                                <table {...props} className="min-w-full divide-y divide-border border border-border rounded-lg" />
                              </div>
                            ),
                            th: ({ ...props }) => (
                              <th {...props} className="px-4 py-3 bg-muted text-left text-sm font-semibold text-foreground border-b border-border" />
                            ),
                            td: ({ ...props }) => (
                              <td {...props} className="px-4 py-3 text-sm text-foreground border-b border-border last:border-b-0" />
                            ),
                            // Better paragraph spacing
                            p: ({ ...props }) => (
                              <p {...props} className="mb-4 leading-relaxed text-foreground" />
                            ),
                            // Better heading styles
                            h1: ({ ...props }) => (
                              <h1 {...props} className="text-2xl font-bold text-foreground mt-8 mb-4" />
                            ),
                            h2: ({ ...props }) => (
                              <h2 {...props} className="text-xl font-semibold text-foreground mt-6 mb-3" />
                            ),
                            h3: ({ ...props }) => (
                              <h3 {...props} className="text-lg font-semibold text-foreground mt-4 mb-2" />
                            ),
                            // Better list styling
                            ul: ({ ...props }) => (
                              <ul {...props} className="list-disc pl-6 mb-4 space-y-1 text-foreground" />
                            ),
                            ol: ({ ...props }) => (
                              <ol {...props} className="list-decimal pl-6 mb-4 space-y-1 text-foreground" />
                            ),
                            // Code blocks
                            pre: ({ ...props }) => (
                              <pre {...props} className="bg-muted p-4 rounded-lg overflow-x-auto mb-4 text-sm" />
                            ),
                            code: ({ ...props }) => (
                              <code {...props} className="bg-muted px-1 py-0.5 rounded text-sm font-mono" />
                            ),
                            // Handle superscript and subscript
                            sup: ({ ...props }) => (
                              <sup {...props} className="text-xs align-super" />
                            ),
                            sub: ({ ...props }) => (
                              <sub {...props} className="text-xs align-sub" />
                            ),
                          }}
                        >
                          {documentContent.content}
                        </ReactMarkdown>
                      </div>
                  ) : (
                    <div className="text-center py-16">
                      <FileText className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
                      <p className="text-foreground text-lg font-medium mb-2">
                        No content available for this document
                      </p>
                      <p className="text-muted-foreground">
                        The document may still be processing or an error occurred during processing
                      </p>
                    </div>
                  )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
