import React from 'react';
import type { Document } from '../types';
import { Button } from '../../../components/ui/button';
import { Paperclip, Trash2 } from 'lucide-react';

interface DocumentListProps {
  documents: Document[];
  onUpload: (file: File) => void;
  onDelete: (documentId: string) => void;
}

const DocumentList: React.FC<DocumentListProps> = ({ documents, onUpload, onDelete }) => {
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  return (
    <div className="p-6 bg-background text-text-primary">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold">Documents</h2>
        <Button asChild>
          <label>
            <Paperclip className="mr-2 h-4 w-4" />
            Upload Document
            <input type="file" className="hidden" onChange={handleFileChange} accept=".pdf" />
          </label>
        </Button>
      </div>
      <div className="bg-background-alt shadow rounded-lg">
        <ul>
          {documents.map((doc) => (
            <li key={doc.id} className="flex justify-between items-center p-4 border-b border-border">
              <span>{doc.original_filename}</span>
              <div className="flex items-center">
                <span className="text-sm text-text-secondary mr-4">{new Date(doc.created_at).toLocaleDateString()}</span>
                <Button variant="ghost" size="icon" onClick={() => onDelete(doc.id)} className="text-destructive hover:text-destructive/80">
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default DocumentList;
