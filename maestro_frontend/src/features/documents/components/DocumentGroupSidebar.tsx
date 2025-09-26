import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Plus, 
  Search,
  FolderOpen,
  FileText,
} from 'lucide-react';
import { getDocumentGroups, createDocumentGroup, renameDocumentGroup, deleteDocumentGroup } from '../api';
import type { DocumentGroupWithCount, DocumentGroup } from '../types';
import { useDocumentContext } from '../context/DocumentContext';
import { Button } from '../../../components/ui/button';
import { ListItem, createEditAction, createDeleteAction } from '../../../components/ui/ListItem';
import { DeleteConfirmationModal } from '../../../components/ui/DeleteConfirmationModal';

interface DocumentGroupSidebarProps {
  onSelectGroup: (group: DocumentGroup | null) => void;
  onGroupCreated?: () => void;
}

export const DocumentGroupSidebar: React.FC<DocumentGroupSidebarProps> = ({
  onSelectGroup,
  onGroupCreated
}) => {
  const { selectedGroup, groupsRefreshKey, refreshGroups } = useDocumentContext();
  const [documentGroups, setDocumentGroups] = useState<DocumentGroupWithCount[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [newGroupName, setNewGroupName] = useState('');
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [groupToDelete, setGroupToDelete] = useState<{ id: string; name: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pageSize = 20;

  useEffect(() => {
    fetchGroups(0);
  }, []);

  // Listen for refresh signals from the context
  useEffect(() => {
    if (groupsRefreshKey > 0) {
      fetchGroups(0);
      setCurrentPage(0);
      setHasMore(true);
    }
  }, [groupsRefreshKey]);

  const fetchGroups = async (page: number = 0, append: boolean = false) => {
    try {
      if (page === 0) {
        setLoading(true);
      } else {
        setIsLoadingMore(true);
      }
      
      const skip = page * pageSize;
      const groups = await getDocumentGroups(skip, pageSize);
      
      if (append) {
        setDocumentGroups(prev => [...prev, ...groups]);
      } else {
        setDocumentGroups(groups);
      }
      
      // Check if we have more pages
      setHasMore(groups.length === pageSize);
      setCurrentPage(page);
      setError(null);
    } catch (err) {
      setError('Failed to fetch document groups.');
      console.error(err);
    } finally {
      setLoading(false);
      setIsLoadingMore(false);
    }
  };
  
  // Handle scroll to load more
  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current || isLoadingMore || !hasMore || loading) return;
    
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    if (scrollTop + clientHeight >= scrollHeight - 100) {
      fetchGroups(currentPage + 1, true);
    }
  }, [currentPage, isLoadingMore, hasMore, loading]);

  const filteredGroups = documentGroups.filter(group =>
    group.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;
    try {
      const newGroup = await createDocumentGroup(newGroupName);
      setNewGroupName('');
      setShowCreateForm(false);
      // Refresh from the beginning to show the new group at the top
      await fetchGroups(0);
      setCurrentPage(0);
      setHasMore(true);
      // Automatically select the newly created group
      const groupWithCount = { ...newGroup, document_count: 0 };
      onSelectGroup(groupWithCount);
      onGroupCreated?.();
    } catch (err) {
      setError('Failed to create document group.');
      console.error(err);
    }
  };

  const handleEditStart = (group: DocumentGroupWithCount, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingGroupId(group.id);
    setEditTitle(group.name);
  };

  const handleEditSave = async (groupId: string) => {
    if (editTitle.trim()) {
      try {
        await renameDocumentGroup(groupId, editTitle.trim());
        // Refresh current data without resetting pagination
        await fetchGroups(0);
        setCurrentPage(0);
        setHasMore(true);
        refreshGroups(); // Notify other components about the group name change
      } catch (err) {
        setError('Failed to rename document group.');
        console.error(err);
      }
    }
    setEditingGroupId(null);
    setEditTitle('');
  };

  const handleEditCancel = () => {
    setEditingGroupId(null);
    setEditTitle('');
  };

  const handleDeleteClick = (groupId: string, groupName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setGroupToDelete({ id: groupId, name: groupName });
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!groupToDelete) return;
    
    try {
      setIsDeleting(true);
      await deleteDocumentGroup(groupToDelete.id);
      // Refresh from the beginning after deletion
      await fetchGroups(0);
      setCurrentPage(0);
      setHasMore(true);
      refreshGroups(); // Notify other components about the group deletion
      if (selectedGroup?.id === groupToDelete.id) {
        onSelectGroup(null);
      }
      
      setDeleteModalOpen(false);
      setGroupToDelete(null);
      setError(null);
    } catch (err) {
      setError('Failed to delete document group.');
      console.error(err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteModalOpen(false);
    setGroupToDelete(null);
    setIsDeleting(false);
  };

  const handleGroupSelect = (group: DocumentGroupWithCount) => {
    onSelectGroup(group);
  };

  const handleViewAllDocuments = () => {
    onSelectGroup(null);
  };

  const formatRelativeTime = (date: string) => {
    const now = new Date();
    const dateObj = new Date(date);
    const diffInHours = Math.floor((now.getTime() - dateObj.getTime()) / (1000 * 60 * 60));
    
    if (diffInHours < 1) return 'Just now';
    if (diffInHours < 24) return `${diffInHours}h ago`;
    if (diffInHours < 48) return 'Yesterday';
    
    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 7) return `${diffInDays}d ago`;
    
    return dateObj.toLocaleDateString();
  };

  return (
    <>
      <div className="flex flex-col h-full bg-sidebar-background">
      {/* Header */}
      <div className="px-4 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center space-x-1.5">
            <FolderOpen className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-medium text-text-primary">Folders</h2>
          </div>
          
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="text-xs h-7 px-2"
          >
            <Plus className="h-3 w-3 mr-1" />
            New Folder
          </Button>
        </div>
      </div>

      {/* Create Group Form */}
      {showCreateForm && (
        <div className="p-4 border-b border-border bg-background">
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Enter group name..."
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateGroup();
                if (e.key === 'Escape') {
                  setShowCreateForm(false);
                  setNewGroupName('');
                }
              }}
              className="w-full px-3 py-2 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-sm bg-background-alt text-text-primary placeholder:text-text-secondary"
              autoFocus
            />
            <div className="flex justify-end space-x-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowCreateForm(false);
                  setNewGroupName('');
                }}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleCreateGroup}
                disabled={!newGroupName.trim()}
                className="text-xs"
              >
                Create
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search groups..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
          />
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mx-4 mt-2 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Groups List */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4"
        onScroll={handleScroll}
      >
        {/* All Documents Option */}
        <div
          className={`group relative p-3 rounded-lg cursor-pointer border transition-colors mb-3 ${
            !selectedGroup 
              ? 'border-primary/30 bg-primary/10' 
              : 'border-border hover:bg-background'
          }`}
          onClick={handleViewAllDocuments}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <FileText className="h-4 w-4 text-text-secondary" />
              <div>
                <div className="font-medium text-sm text-text-primary">
                  All Documents
                </div>
                <div className="text-xs text-text-secondary">
                  View all documents in library
                </div>
              </div>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8">
            <div className="text-text-secondary text-sm">Loading groups...</div>
          </div>
        ) : filteredGroups.length === 0 ? (
          <div className="text-center py-8">
            <FolderOpen className="h-12 w-12 text-muted-foreground/20 mx-auto mb-4" />
            <p className="text-text-secondary text-sm">
              {searchQuery ? 'No groups found' : 'No groups yet'}
            </p>
            {!searchQuery && (
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setShowCreateForm(true)}
                className="mt-2"
              >
                Create your first group
              </Button>
            )}
          </div>
        ) : (
          <>
            <div className="space-y-1">
            {filteredGroups.map((group) => {
              const isActive = selectedGroup?.id === group.id;
              
              if (editingGroupId === group.id) {
                return (
                  <div
                    key={group.id}
                    className="p-2 rounded-md border border-primary bg-primary/5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSave(group.id);
                        if (e.key === 'Escape') handleEditCancel();
                      }}
                      onBlur={() => handleEditSave(group.id)}
                      className="w-full text-xs font-medium bg-background border border-border rounded px-2 py-1 focus:ring-2 focus:ring-primary focus:border-transparent"
                      autoFocus
                    />
                  </div>
                )
              }

              const actions = [
                createEditAction((e: React.MouseEvent) => handleEditStart(group, e)),
                createDeleteAction((e: React.MouseEvent) => handleDeleteClick(group.id, group.name, e))
              ]

              const metadata = [
                {
                  icon: <FileText className="h-3 w-3" />,
                  text: `${group.document_count} document${group.document_count !== 1 ? 's' : ''}`
                }
              ]
              
              return (
                <ListItem
                  key={group.id}
                  isSelected={isActive}
                  onClick={() => handleGroupSelect(group)}
                  icon={<FolderOpen className="h-4 w-4" />}
                  title={group.name}
                  timestamp={formatRelativeTime(group.updated_at)}
                  metadata={metadata}
                  actions={actions}
                  showActionsPermanently={true}
                />
              )
            })}
            </div>
            
            {/* Loading more indicator */}
            {isLoadingMore && (
              <div className="text-center py-4">
                <div className="text-text-secondary text-sm">Loading more groups...</div>
              </div>
            )}
            
            {/* No more groups indicator */}
            {!hasMore && documentGroups.length > 0 && (
              <div className="text-center py-4">
                <div className="text-text-tertiary text-xs">No more groups to load</div>
              </div>
            )}
          </>
        )}
      </div>
      </div>

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Folder"
        description="Are you sure you want to delete this folder? This will not delete the documents themselves, only the folder organization."
        itemName={groupToDelete?.name}
        itemType="item"
        isLoading={isDeleting}
      />
    </>
  );
};
