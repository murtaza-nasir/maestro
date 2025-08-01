import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Button } from '../../../components/ui/button';
import { Card, CardContent } from '../../../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { Input } from '../../../components/ui/input';
import { FileText, Save, Download, Eye, Edit3, BookOpen, RefreshCw, Copy, Edit2, Check, X, CheckCheck } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import SimpleMDE from 'react-simplemde-editor';
import type { Options } from 'easymde';
import 'easymde/dist/easymde.min.css';
import './editor.css';
import { ReferencePanel } from './ReferencePanel';
import { useWritingStore } from '../store';
import { useDebounce } from '../../../hooks/useDebounce';
import * as writingApi from '../api';
import { WritingSessionStats } from './WritingSessionStats';
import { useTheme } from '../../../contexts/ThemeContext';

export const DraftPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState('editor');
  const previousTabRef = useRef('editor');
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  
  // Local editor state - this is the source of truth for the editor content
  const [localContent, setLocalContent] = useState('');
  const [isUserEditing, setIsUserEditing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  
  // Title editing state
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [localTitle, setLocalTitle] = useState('');
  
  // Copy feedback state
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'success' | 'error'>('idle');
  
  // Editor instance and cursor position preservation
  const editorInstanceRef = useRef<any>(null);
  const lastCursorPositionRef = useRef<{ line: number; ch: number } | null>(null);
  const isExternalUpdateRef = useRef(false);
  
  // Debounced content for auto-save
  const debouncedContent = useDebounce(localContent, 2000);
  
  const {
    currentDraft,
    currentSession,
    setCurrentDraft,
    getSessionLoading,
    saveDraftChanges,
  } = useWritingStore();
  
  // Get loading state for current session
  const isLoading = currentSession ? getSessionLoading(currentSession.id) : false;
  const { theme } = useTheme();

  // Initialize local content and title when draft changes
  useEffect(() => {
    if (currentDraft) {
      console.log('Draft changed, updating local state:', currentDraft.id);
      
      // Force update content when draft changes to ensure proper isolation
      const newContent = currentDraft.content || '';
      console.log('Updating local content from draft:', newContent.length, 'characters');
      setLocalContent(newContent);
      setHasUnsavedChanges(false);
      setIsUserEditing(false); // Reset editing state when draft changes
      
      // Always update title when draft changes (unless user is editing title)
      if (!isEditingTitle) {
        const newTitle = currentDraft.title || 'Untitled Document';
        console.log('Updating local title from draft:', newTitle);
        setLocalTitle(newTitle);
      }
    } else {
      // Clear local state when no draft is selected
      console.log('No current draft, clearing local state');
      setLocalContent('');
      setHasUnsavedChanges(false);
      setIsUserEditing(false);
      if (!isEditingTitle) {
        setLocalTitle('Untitled Document');
      }
    }
  }, [currentDraft?.id, currentDraft?.content, currentDraft?.title, isEditingTitle]);

  // Save draft function
  const handleSaveDraft = useCallback(async (content: string, title?: string) => {
    if (!currentDraft || !currentSession || isSaving) return;
    
    console.log('Saving draft...');
    setIsSaving(true);
    
    try {
      await writingApi.updateSessionDraft(currentSession.id, {
        title: title || currentDraft.title,
        content: content,
      });
      
      setLastSaved(new Date());
      setHasUnsavedChanges(false);
      
      // Update the store optimistically without triggering editor re-render
      setCurrentDraft({ ...currentDraft, content, title: title || currentDraft.title });
      
      console.log('Draft saved successfully');
    } catch (error) {
      console.error('Failed to save draft:', error);
    } finally {
      setIsSaving(false);
    }
  }, [currentDraft, currentSession, isSaving, setCurrentDraft]);

  // Title editing functions
  const handleStartEditingTitle = useCallback(() => {
    if (currentDraft) {
      setLocalTitle(currentDraft.title || 'Untitled Document');
      setIsEditingTitle(true);
    }
  }, [currentDraft]);

  const handleSaveTitle = useCallback(async () => {
    if (!currentDraft || !currentSession || !localTitle.trim()) return;
    
    try {
      await handleSaveDraft(localContent, localTitle.trim());
      setIsEditingTitle(false);
    } catch (error) {
      console.error('Failed to save title:', error);
    }
  }, [currentDraft, currentSession, localTitle, localContent, handleSaveDraft]);

  const handleCancelEditingTitle = useCallback(() => {
    if (currentDraft) {
      setLocalTitle(currentDraft.title || 'Untitled Document');
    }
    setIsEditingTitle(false);
  }, [currentDraft]);

  const handleTitleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveTitle();
    } else if (e.key === 'Escape') {
      handleCancelEditingTitle();
    }
  }, [handleSaveTitle, handleCancelEditingTitle]);

  // Auto-save when debounced content changes
  useEffect(() => {
    if (hasUnsavedChanges && debouncedContent && currentDraft && currentSession && !isUserEditing) {
      // Only auto-save if the content actually belongs to the current draft
      // and the user is not actively editing (to prevent race conditions)
      console.log('Auto-saving due to debounced content change for draft:', currentDraft.id);
      handleSaveDraft(debouncedContent);
    }
  }, [debouncedContent, hasUnsavedChanges, currentDraft?.id, currentSession?.id, isUserEditing, handleSaveDraft]);

  // Preserve cursor position during external updates
  const preserveCursorPosition = useCallback(() => {
    if (editorInstanceRef.current?.codemirror) {
      lastCursorPositionRef.current = editorInstanceRef.current.codemirror.getCursor();
    }
  }, []);

  const restoreCursorPosition = useCallback(() => {
    if (editorInstanceRef.current?.codemirror && lastCursorPositionRef.current) {
      const cm = editorInstanceRef.current.codemirror;
      // Use setTimeout to ensure the content has been updated first
      setTimeout(() => {
        try {
          cm.setCursor(lastCursorPositionRef.current);
          cm.focus();
        } catch (error) {
          console.warn('Could not restore cursor position:', error);
        }
      }, 0);
    }
  }, []);

  // Handle content changes from the editor
  const handleContentChange = useCallback((value: string) => {
    if (!isExternalUpdateRef.current) {
      setLocalContent(value);
      setHasUnsavedChanges(true);
      
      // Mark that user is actively editing
      if (!isUserEditing) {
        setIsUserEditing(true);
      }
    }
  }, [isUserEditing]);

  // Handle editor instance initialization
  const handleEditorDidMount = useCallback((editor: any) => {
    if (editor?.codemirror) {
      editorInstanceRef.current = editor;
      const cm = editor.codemirror;
      
      console.log('Editor mounted and CodeMirror instance stored');
      
      // Set up event listeners for user interaction detection
      cm.on('focus', () => {
        console.log('Editor focused - user is editing');
        setIsUserEditing(true);
      });
      
      cm.on('blur', () => {
        console.log('Editor blurred - user stopped editing');
        setIsUserEditing(false);
        
        // Save immediately on blur if there are unsaved changes
        if (hasUnsavedChanges && currentDraft && currentSession) {
          handleSaveDraft(localContent);
        }
      });
      
      // Track cursor movements to preserve position
      cm.on('cursorActivity', () => {
        if (!isExternalUpdateRef.current) {
          lastCursorPositionRef.current = cm.getCursor();
        }
      });
      
      // Detect when user starts typing
      cm.on('beforeChange', () => {
        if (!isExternalUpdateRef.current) {
          setIsUserEditing(true);
        }
      });
    }
  }, [hasUnsavedChanges, currentDraft, currentSession, localContent, handleSaveDraft]);

  // Manual save handler
  const handleManualSave = useCallback(() => {
    if (currentDraft && currentSession) {
      handleSaveDraft(localContent);
    }
  }, [currentDraft, currentSession, localContent, handleSaveDraft]);

  // Copy to clipboard with feedback
  const handleCopyToClipboard = useCallback(async () => {
    if (!localContent) return;
    
    setCopyStatus('copying');
    
    try {
      // Try modern clipboard API first
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(localContent);
        console.log('Content copied to clipboard using modern API');
      } else {
        // Fallback to legacy method
        const textArea = document.createElement('textarea');
        textArea.value = localContent;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (!successful) {
          throw new Error('Legacy copy method failed');
        }
        console.log('Content copied to clipboard using legacy method');
      }
      
      // Show success feedback
      setCopyStatus('success');
      
      // Reset to idle after 2 seconds
      setTimeout(() => {
        setCopyStatus('idle');
      }, 2000);
      
    } catch (error) {
      console.error('Failed to copy content to clipboard:', error);
      setCopyStatus('error');
      
      // Reset to idle after 3 seconds
      setTimeout(() => {
        setCopyStatus('idle');
      }, 3000);
    }
  }, [localContent]);

  // Export draft
  const handleExportDraft = useCallback(() => {
    if (!currentDraft) return;
    
    let content = `# ${currentDraft.title || 'Untitled Document'}\n\n`;
    content += localContent || '';
    
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentDraft.title || 'document'}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [currentDraft, localContent]);

  // Refresh draft
  const handleRefreshDraft = useCallback(async () => {
    if (!currentSession) return;
    
    try {
      // Preserve cursor position before refresh
      preserveCursorPosition();
      
      const updatedDraft = await writingApi.getSessionDraft(currentSession.id);
      setCurrentDraft(updatedDraft);
      
      // If user is not editing, update local content
      if (!isUserEditing) {
        isExternalUpdateRef.current = true;
        setLocalContent(updatedDraft.content || '');
        setHasUnsavedChanges(false);
        
        // Restore cursor position after content update
        setTimeout(() => {
          restoreCursorPosition();
          isExternalUpdateRef.current = false;
        }, 100);
      }
    } catch (error) {
      console.error('Failed to refresh draft:', error);
    }
  }, [currentSession, isUserEditing, preserveCursorPosition, restoreCursorPosition, setCurrentDraft]);

  // Word and reference counts
  const getWordCount = useCallback(() => {
    if (!localContent) return 0;
    return localContent.split(/\s+/).filter(Boolean).length;
  }, [localContent]);

  const getReferenceCount = useCallback(() => {
    if (!currentDraft) return 0;
    return currentDraft.references?.length || 0;
  }, [currentDraft]);

  // Editor options
  const editorOptions = useMemo(() => {
    return {
      autofocus: false,
      spellChecker: false,
      toolbar: [
        'bold', 'italic', 'heading', '|',
        'quote', 'unordered-list', 'ordered-list', '|',
        'link', 'image', '|',
        'guide'
      ],
      status: true,
      maxHeight: '100%',
    } as Options;
  }, []);

  // Handle tab changes
  const handleTabChange = useCallback((value: string) => {
    // Save content when switching away from editor tab if there are unsaved changes
    if (previousTabRef.current === 'editor' && value !== 'editor' && 
        hasUnsavedChanges && currentDraft && currentSession) {
      handleSaveDraft(localContent);
    }
    
    previousTabRef.current = activeTab;
    setActiveTab(value);
  }, [activeTab, hasUnsavedChanges, currentDraft, currentSession, localContent, handleSaveDraft]);

  // Global save function for chat switching
  const saveCurrentChanges = useCallback(async () => {
    if (hasUnsavedChanges && currentDraft && currentSession && localContent) {
      console.log('Saving current changes before chat switch...');
      try {
        await saveDraftChanges(localContent, localTitle);
        setHasUnsavedChanges(false);
        console.log('Changes saved successfully before chat switch');
        return true;
      } catch (error) {
        console.error('Failed to save changes before chat switch:', error);
        return false;
      }
    }
    return true; // No changes to save
  }, [hasUnsavedChanges, currentDraft, currentSession, localContent, localTitle, saveDraftChanges]);

  // Register global save function
  useEffect(() => {
    // Store the save function globally so other components can call it
    (window as any).saveCurrentDraftChanges = saveCurrentChanges;
    
    return () => {
      // Clean up on unmount
      delete (window as any).saveCurrentDraftChanges;
    };
  }, [saveCurrentChanges]);

  return (
    <div className={`h-full flex flex-col bg-background text-text-primary ${theme}`}>
      {/* Header */}
      <div className="p-4 border-b border-border bg-header-background">
        {/* Draft Info */}
        {currentDraft ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                {/* Editable Title */}
                <div className="flex items-center gap-2">
                  {isEditingTitle ? (
                    <div className="flex items-center gap-1 flex-1">
                      <Input
                        value={localTitle}
                        onChange={(e) => setLocalTitle(e.target.value)}
                        onKeyDown={handleTitleKeyPress}
                        className="text-sm font-medium h-6 px-2 py-1 bg-background-alt border-border"
                        autoFocus
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleSaveTitle}
                        className="h-6 w-6 p-0 text-text-secondary hover:text-text-primary hover:bg-muted"
                      >
                        <Check className="h-3 w-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleCancelEditingTitle}
                        className="h-6 w-6 p-0 text-text-secondary hover:text-text-primary hover:bg-muted"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">
                        {currentDraft.title || 'Untitled Document'}
                      </p>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleStartEditingTitle}
                        className="h-5 w-5 p-0 text-text-secondary hover:text-text-primary hover:bg-muted flex-shrink-0"
                      >
                        <Edit2 className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              
              {/* Action Icons */}
              <div className="flex items-center space-x-1 ml-4">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={handleRefreshDraft}
                  disabled={isLoading}
                  className="h-6 w-6 p-0 text-text-secondary hover:text-text-primary hover:bg-muted rounded"
                  title="Refresh draft"
                >
                  <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopyToClipboard}
                  disabled={!currentDraft || copyStatus === 'copying'}
                  className={`h-6 w-6 p-0 rounded transition-colors duration-200 ${
                    copyStatus === 'success' 
                      ? 'text-green-500 hover:text-green-600 hover:bg-green-500/10' 
                      : copyStatus === 'error'
                      ? 'text-destructive hover:text-destructive/80 hover:bg-destructive/10'
                      : 'text-text-secondary hover:text-text-primary hover:bg-muted'
                  }`}
                  title={
                    copyStatus === 'copying' 
                      ? 'Copying...' 
                      : copyStatus === 'success' 
                      ? 'Copied!' 
                      : copyStatus === 'error'
                      ? 'Copy failed'
                      : 'Copy to clipboard'
                  }
                >
                  {copyStatus === 'success' ? (
                    <CheckCheck className="h-3 w-3" />
                  ) : copyStatus === 'error' ? (
                    <X className="h-3 w-3" />
                  ) : (
                    <Copy className={`h-3 w-3 ${copyStatus === 'copying' ? 'animate-pulse' : ''}`} />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleManualSave}
                  disabled={!currentDraft || isSaving || !hasUnsavedChanges}
                  className="h-6 w-6 p-0 text-text-secondary hover:text-text-primary hover:bg-muted rounded"
                  title={isSaving ? 'Saving...' : 'Save draft'}
                >
                  <Save className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleExportDraft}
                  disabled={!currentDraft}
                  className="h-6 w-6 p-0 text-text-secondary hover:text-text-primary hover:bg-muted rounded"
                  title="Export as markdown"
                >
                  <Download className="h-3 w-3" />
                </Button>
              </div>
            </div>
            
            {/* Document Info */}
            <div className="flex items-center justify-between text-xs text-text-secondary">
              <div>
                {getWordCount()} words • {getReferenceCount()} references
              </div>
              <div className="flex items-end">
                <div>
                  {isSaving 
                    ? 'Saving...' 
                    : hasUnsavedChanges 
                    ? <span className="text-amber-500">Unsaved changes (auto-save in progress)</span>
                    : lastSaved 
                    ? `Saved ${lastSaved.toLocaleTimeString()}` 
                    : 'Ready'
                  }
                </div>
              </div>
            </div>
          </div>
        ) : (
          <Card className="bg-background-alt border-border">
            <CardContent className="p-6">
              <div className="text-center text-text-secondary">
                <FileText className="h-12 w-12 mx-auto mb-4 text-text-tertiary" />
                <h3 className="text-lg font-medium text-text-primary mb-2">No Document Selected</h3>
                <p className="text-sm">
                  Select a document group and start a writing session to begin editing.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Writing Session Stats */}
        {currentSession && (
          <div className="mt-3">
            <WritingSessionStats sessionId={currentSession.id} />
          </div>
        )}
      </div>

      {/* Content Tabs */}
      <div className="flex-1 overflow-hidden">
        <Tabs value={activeTab} onValueChange={handleTabChange} className="h-full flex flex-col">
          <TabsList className="grid w-full grid-cols-3 bg-secondary h-8 p-0.5">
            <TabsTrigger value="editor" className="flex items-center gap-1.5 h-7 px-2 text-xs rounded-md">
              <Edit3 className="h-3 w-3" />
              <span className="hidden sm:inline">Editor</span>
            </TabsTrigger>
            <TabsTrigger value="preview" className="flex items-center gap-1.5 h-7 px-2 text-xs rounded-md">
              <Eye className="h-3 w-3" />
              <span className="hidden sm:inline">Preview</span>
            </TabsTrigger>
            <TabsTrigger value="references" className="flex items-center gap-1.5 h-7 px-2 text-xs rounded-md">
              <BookOpen className="h-3 w-3" />
              <span className="hidden sm:inline">References</span>
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-hidden">
            <TabsContent value="editor" className="h-full m-0 relative overflow-hidden">
              {currentDraft ? (
                <div className={`absolute inset-0 editor-container ${theme}`} style={{ top: 0 }}>
                  <SimpleMDE
                    key={currentDraft.id} // Force re-mount when draft changes
                    value={localContent}
                    onChange={handleContentChange}
                    options={editorOptions}
                    className="h-full"
                    getCodemirrorInstance={handleEditorDidMount}
                  />
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-text-secondary">
                  <p>No draft available</p>
                </div>
              )}
            </TabsContent>

            <TabsContent value="preview" className="h-full m-0 p-4 overflow-y-auto">
              <div className="prose dark:prose-invert max-w-none" style={{ fontSize: '13px', lineHeight: '1.4' }}>
                {currentDraft ? (
                  <ReactMarkdown
                    components={{
                      // Compact headings
                      h1: ({node, ...props}) => <h1 {...props} className="text-lg font-bold mb-2 mt-3 first:mt-0" />,
                      h2: ({node, ...props}) => <h2 {...props} className="text-base font-semibold mb-2 mt-2 first:mt-0" />,
                      h3: ({node, ...props}) => <h3 {...props} className="text-sm font-medium mb-1 mt-2 first:mt-0" />,
                      h4: ({node, ...props}) => <h4 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                      h5: ({node, ...props}) => <h5 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                      h6: ({node, ...props}) => <h6 {...props} className="text-xs font-medium mb-1 mt-1 first:mt-0" />,
                      // Compact paragraphs - match editor font size
                      p: ({node, ...props}) => <p {...props} className="mb-2 last:mb-0" style={{ fontSize: '13px', lineHeight: '1.4' }} />,
                      // Compact lists - match editor font size
                      ul: ({node, ...props}) => <ul {...props} className="my-2 space-y-0.5" />,
                      ol: ({node, ...props}) => <ol {...props} className="my-2 space-y-0.5" />,
                      li: ({node, ...props}) => <li {...props} style={{ fontSize: '13px', lineHeight: '1.4' }} />,
                      // Compact blockquotes - match editor font size
                      blockquote: ({node, ...props}) => <blockquote {...props} className="border-l-4 border-border pl-3 my-2 italic" style={{ fontSize: '13px', lineHeight: '1.4' }} />,
                      // Compact code
                      code: ({node, className, children, ...props}) => {
                        const match = /language-(\w+)/.exec(className || '')
                        const isInline = !match
                        
                        if (isInline) {
                          return (
                            <code {...props} className="px-1 py-0.5 rounded text-xs font-mono bg-muted">
                              {children}
                            </code>
                          )
                        }
                        
                        return (
                          <pre className="bg-code-background text-code-foreground p-3 rounded-lg overflow-x-auto my-2">
                            <code className="text-xs font-mono whitespace-pre">
                              {children}
                            </code>
                          </pre>
                        )
                      },
                      // Compact tables
                      table: ({node, ...props}) => (
                        <div className="overflow-x-auto my-2">
                          <table {...props} className="min-w-full border-collapse border border-border text-sm" />
                        </div>
                      ),
                      th: ({node, ...props}) => (
                        <th {...props} className="border border-border px-2 py-1 bg-muted font-medium text-left text-xs" />
                      ),
                      td: ({node, ...props}) => (
                        <td {...props} className="border border-border px-2 py-1 text-xs" />
                      ),
                      // Compact horizontal rules
                      hr: ({node, ...props}) => <hr {...props} className="my-2 border-border" />,
                    }}
                  >
                    {localContent}
                  </ReactMarkdown>
                ) : (
                  <div className="h-full flex items-center justify-center text-text-secondary">
                    <p>No draft available for preview</p>
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="references" className="h-full m-0">
              <ReferencePanel references={currentDraft?.references || []} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
};
