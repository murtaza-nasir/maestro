import React, { useState, useCallback, useRef } from 'react';
import { Upload } from 'lucide-react';
import { cn } from '../../../lib/utils';

export interface UploadFile {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error' | 'cancelled';
  progress: number;
  error?: string;
  documentId?: string;
}

interface DocumentUploadZoneProps {
  selectedGroupId?: string;
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
  maxFiles?: number;
  maxFileSize?: number; // in MB
}

export const DocumentUploadZone: React.FC<DocumentUploadZoneProps> = ({
  selectedGroupId,
  onFilesSelected,
  disabled = false,
  maxFiles = 10,
  maxFileSize = 100 // 100MB default
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    const supportedExtensions = ['.pdf', '.docx', '.doc', '.md', '.markdown'];
    const fileName = file.name.toLowerCase();
    
    // Debug logging
    console.log(`Validating file: ${file.name}, size: ${file.size}, type: ${file.type}`);
    
    if (!supportedExtensions.some(ext => fileName.endsWith(ext))) {
      const error = `Only PDF, Word (docx, doc), and Markdown (md, markdown) files are supported. Got: ${file.name}`;
      console.error('File validation failed:', error);
      return error;
    }
    if (file.size > maxFileSize * 1024 * 1024) {
      const error = `File size must be less than ${maxFileSize}MB. Got: ${(file.size / 1024 / 1024).toFixed(2)}MB`;
      console.error('File size validation failed:', error);
      return error;
    }
    
    console.log(`File validation passed: ${file.name}`);
    return null;
  };

  const handleFiles = useCallback((files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const validFiles: File[] = [];
    const errors: string[] = [];

    fileArray.forEach(file => {
      const error = validateFile(file);
      if (error) {
        errors.push(`${file.name}: ${error}`);
      } else {
        validFiles.push(file);
      }
    });

    if (errors.length > 0) {
      console.error('File validation errors:', errors);
      // Show alert for now - TODO: Replace with proper toast notifications
      alert(`File validation errors:\n${errors.join('\n')}`);
    }

    if (validFiles.length > 0) {
      console.log(`Calling onFilesSelected with ${validFiles.length} valid files:`, validFiles.map(f => f.name));
      onFilesSelected(validFiles);
    } else if (errors.length > 0) {
      console.log('No valid files to upload due to validation errors');
    }
  }, [maxFiles, maxFileSize, onFilesSelected]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set drag over to false if we're leaving the drop zone itself
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    if (disabled) {
      console.log('Upload zone is disabled, ignoring drop');
      return;
    }

    if (!selectedGroupId) {
      console.log('No group selected, ignoring drop');
      alert('Please select a document group first before uploading files');
      return;
    }

    const files = e.dataTransfer.files;
    console.log(`Files dropped: ${files.length} files`, Array.from(files).map(f => `${f.name} (${f.type})`));
    
    if (files && files.length > 0) {
      handleFiles(files);
    } else {
      console.log('No files in drop event');
    }
  }, [disabled, selectedGroupId, handleFiles]);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFiles(files);
    }
    // Reset input value to allow selecting the same file again
    e.target.value = '';
  }, [handleFiles]);

  const handleClick = useCallback(() => {
    if (disabled) {
      console.log('Upload zone is disabled, ignoring click');
      return;
    }
    
    if (!selectedGroupId) {
      console.log('No group selected, ignoring click');
      alert('Please select a document group first before uploading files');
      return;
    }
    
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled, selectedGroupId]);

  return (
    <div className="space-y-4">
      {/* Upload Zone */}
      <div
        className={cn(
          "relative border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
          isDragOver && !disabled
            ? "border-primary bg-primary/10"
            : "border-border hover:border-primary/50",
          disabled && "opacity-50 cursor-not-allowed",
          !selectedGroupId && "opacity-50 cursor-not-allowed"
        )}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.md,.markdown"
          onChange={handleFileInputChange}
          className="hidden"
          disabled={disabled || !selectedGroupId}
        />
        
        <div className="flex flex-col items-center space-y-4">
          <div className={cn(
            "p-4 rounded-full",
            isDragOver ? "bg-primary/20" : "bg-muted"
          )}>
            <Upload className={cn(
              "h-8 w-8",
              isDragOver ? "text-primary" : "text-text-secondary"
            )} />
          </div>
          
          <div className="space-y-2">
            <h3 className="text-lg font-medium text-text-primary">
              {isDragOver ? "Drop files here" : "Upload Documents"}
            </h3>
            <p className="text-sm text-text-secondary">
              {!selectedGroupId 
                ? "Select a document group first"
                : `Drag and drop PDF, Word, or Markdown files here, or click to browse`
              }
            </p>
            <p className="text-xs text-text-tertiary">
              Maximum {maxFiles} files, up to {maxFileSize}MB each • Supported: PDF, DOCX, DOC, MD
            </p>
          </div>
        </div>
      </div>

    </div>
  );
};
