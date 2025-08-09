import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Plus, X, Save, Loader2 } from 'lucide-react';
import type { Document } from '../types';
import type { DocumentMetadataUpdate } from '../api';
import { updateDocumentMetadata } from '../api';

interface DocumentMetadataEditModalProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updatedDocument: Document) => void;
}

export const DocumentMetadataEditModal: React.FC<DocumentMetadataEditModalProps> = ({
  document,
  isOpen,
  onClose,
  onSave,
}) => {
  const [formData, setFormData] = useState<DocumentMetadataUpdate>({
    title: '',
    authors: [],
    journal_or_source: '',
    publication_year: undefined,
    abstract: '',
    keywords: [],
  });
  const [newAuthor, setNewAuthor] = useState('');
  const [newKeyword, setNewKeyword] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize form data when document changes
  useEffect(() => {
    if (document) {
      const metadata = document.metadata_ || {};
      
      // Handle authors - could be string or array
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

      setFormData({
        title: document.title || metadata.title || '',
        authors: authorsArray,
        journal_or_source: metadata.journal_or_source || '',
        publication_year: metadata.publication_year || undefined,
        abstract: metadata.abstract || '',
        keywords: metadata.keywords || [],
      });
    }
  }, [document]);

  const handleInputChange = (field: keyof DocumentMetadataUpdate, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleAddAuthor = () => {
    if (newAuthor.trim()) {
      setFormData(prev => ({
        ...prev,
        authors: [...(prev.authors || []), newAuthor.trim()],
      }));
      setNewAuthor('');
    }
  };

  const handleRemoveAuthor = (index: number) => {
    setFormData(prev => ({
      ...prev,
      authors: (prev.authors || []).filter((_, i) => i !== index),
    }));
  };

  const handleAddKeyword = () => {
    if (newKeyword.trim()) {
      setFormData(prev => ({
        ...prev,
        keywords: [...(prev.keywords || []), newKeyword.trim()],
      }));
      setNewKeyword('');
    }
  };

  const handleRemoveKeyword = (index: number) => {
    setFormData(prev => ({
      ...prev,
      keywords: (prev.keywords || []).filter((_, i) => i !== index),
    }));
  };

  const handleSave = async () => {
    if (!document) return;

    setIsSaving(true);
    setError(null);

    try {
      // Clean up the form data - remove undefined/empty values
      const cleanedData: DocumentMetadataUpdate = {};
      
      if (formData.title?.trim()) cleanedData.title = formData.title.trim();
      if (formData.authors && formData.authors.length > 0) cleanedData.authors = formData.authors;
      if (formData.journal_or_source?.trim()) cleanedData.journal_or_source = formData.journal_or_source.trim();
      if (formData.publication_year) cleanedData.publication_year = formData.publication_year;
      if (formData.abstract?.trim()) cleanedData.abstract = formData.abstract.trim();
      if (formData.keywords && formData.keywords.length > 0) cleanedData.keywords = formData.keywords;

      const updatedDocument = await updateDocumentMetadata(document.id, cleanedData);
      onSave(updatedDocument);
      onClose();
    } catch (err: any) {
      console.error('Error updating document metadata:', err);
      setError(err.response?.data?.detail || 'Failed to update document metadata');
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = () => {
    setError(null);
    onClose();
  };

  if (!document) return null;

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] p-0 flex flex-col">
        <DialogHeader className="px-4 pt-4 pb-3 border-b border-border">
          <DialogTitle className="text-lg font-semibold text-foreground">Edit Document Metadata</DialogTitle>
          <p className="text-sm text-muted-foreground mt-1">
            {document.original_filename}
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {error && (
              <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 text-destructive">
                <p className="font-medium">Error updating metadata</p>
                <p className="text-sm mt-1">{error}</p>
              </div>
            )}

            {/* Title Section */}
            <div className="bg-muted/20 rounded-lg p-4 border border-border">
              <div className="space-y-3">
                <Label htmlFor="title" className="text-sm font-semibold text-foreground">Document Title</Label>
                <Input
                  id="title"
                  value={formData.title || ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleInputChange('title', e.target.value)}
                  placeholder="Enter document title"
                />
              </div>
            </div>

            {/* Authors Section */}
            <div className="bg-muted/20 rounded-lg p-4 border border-border">
              <div className="space-y-3">
                <Label className="text-sm font-semibold text-foreground">Authors</Label>
                <div className="space-y-2">
                  {(formData.authors || []).map((author, index) => (
                    <div key={index} className="flex items-center gap-2 p-2 bg-background rounded-lg border border-border">
                      <Input
                        value={author}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          const newAuthors = [...(formData.authors || [])];
                          newAuthors[index] = e.target.value;
                          handleInputChange('authors', newAuthors);
                        }}
                        className="flex-1"
                        placeholder="Author name"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => handleRemoveAuthor(index)}
                        className="text-destructive hover:text-destructive-foreground hover:bg-destructive"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 p-2 bg-background/50 rounded-lg border-2 border-dashed border-border">
                    <Input
                      value={newAuthor}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewAuthor(e.target.value)}
                      placeholder="Add new author"
                      className="flex-1"
                      onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleAddAuthor()}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAddAuthor}
                      className="text-primary hover:bg-primary hover:text-primary-foreground"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            {/* Publication Details Section */}
            <div className="bg-muted/20 rounded-lg p-4 border border-border">
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-foreground mb-2">Publication Details</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="journal" className="text-sm font-medium text-foreground">Journal/Source</Label>
                    <Input
                      id="journal"
                      value={formData.journal_or_source || ''}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleInputChange('journal_or_source', e.target.value)}
                      placeholder="Enter journal or publication source"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="year" className="text-sm font-medium text-foreground">Publication Year</Label>
                    <Input
                      id="year"
                      type="number"
                      value={formData.publication_year || ''}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleInputChange('publication_year', e.target.value ? parseInt(e.target.value) : undefined)}
                      placeholder="Enter publication year"
                      min="1900"
                      max={new Date().getFullYear() + 1}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Keywords Section */}
            <div className="bg-muted/20 rounded-lg p-4 border border-border">
              <div className="space-y-3">
                <Label className="text-sm font-semibold text-foreground">Keywords</Label>
                <div className="space-y-2">
                  {(formData.keywords || []).map((keyword, index) => (
                    <div key={index} className="flex items-center gap-2 p-2 bg-background rounded-lg border border-border">
                      <Input
                        value={keyword}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          const newKeywords = [...(formData.keywords || [])];
                          newKeywords[index] = e.target.value;
                          handleInputChange('keywords', newKeywords);
                        }}
                        className="flex-1"
                        placeholder="Keyword"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => handleRemoveKeyword(index)}
                        className="text-destructive hover:text-destructive-foreground hover:bg-destructive"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 p-2 bg-background/50 rounded-lg border-2 border-dashed border-border">
                    <Input
                      value={newKeyword}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKeyword(e.target.value)}
                      placeholder="Add new keyword"
                      className="flex-1"
                      onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleAddKeyword()}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAddKeyword}
                      className="text-primary hover:bg-primary hover:text-primary-foreground"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            {/* Abstract Section */}
            <div className="bg-muted/20 rounded-lg p-4 border border-border">
              <div className="space-y-3">
                <Label htmlFor="abstract" className="text-sm font-semibold text-foreground">Abstract</Label>
                <textarea
                  id="abstract"
                  value={formData.abstract || ''}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => handleInputChange('abstract', e.target.value)}
                  placeholder="Enter document abstract"
                  rows={5}
                  className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
                />
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="px-4 py-3 border-t border-border bg-muted/10 pt-4">
          <div className="flex items-center gap-3 w-full justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isSaving}
              size="sm"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              size="sm"
            >
              {isSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Save Changes
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
