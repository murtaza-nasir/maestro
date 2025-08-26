import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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

  useEffect(() => {
    fetchGroups();
  }, []);

  useEffect(() => {
    if (groupsRefreshKey > 0) {
      fetchGroups();
    }
  }, [groupsRefreshKey]);

  const fetchGroups = async () => {
    try {
      setLoading(true);
      const groups = await getDocumentGroups();
      setDocumentGroups(groups);
      setError(null);
    } catch (err) {
      setError(t('documentGroupSidebar.failedToFetch'));
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const filteredGroups = documentGroups.filter(group =>
    group.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;
    try {
      const newGroup = await createDocumentGroup(newGroupName);
      setNewGroupName('');
      setShowCreateForm(false);
      await fetchGroups();
      const groupWithCount = { ...newGroup, document_count: 0 };
      onSelectGroup(groupWithCount);
      onGroupCreated?.();
    } catch (err) {
      setError(t('documentGroupSidebar.failedToCreate'));
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
        await fetchGroups();
        refreshGroups();
      } catch (err) {
        setError(t('documentGroupSidebar.failedToRename'));
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
      await fetchGroups();
      refreshGroups();
      if (selectedGroup?.id === groupToDelete.id) {
        onSelectGroup(null);
      }
      
      setDeleteModalOpen(false);
      setGroupToDelete(null);
      setError(null);
    } catch (err) {
      setError(t('documentGroupSidebar.failedToDelete'));
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
    
    if (diffInHours < 1) return t('documentGroupSidebar.justNow');
    if (diffInHours < 24) return t('documentGroupSidebar.hoursAgo', { count: diffInHours });
    if (diffInHours < 48) return t('documentGroupSidebar.yesterday');
    
    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 7) return t('documentGroupSidebar.daysAgo', { count: diffInDays });
    
    return dateObj.toLocaleDateString();
  };

  return (
    <>
      <div className="flex flex-col h-full bg-sidebar-background">
        <div className="px-4 py-4 border-b border-border min-h-[88px] flex items-center bg-header-background">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-1.5">
              <FolderOpen className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-medium text-text-primary">{t('documentGroupSidebar.folders')}</h2>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="text-xs h-7 px-2"
            >
              <Plus className="h-3 w-3 mr-1" />
              {t('documentGroupSidebar.newFolder')}
            </Button>
          </div>
        </div>

        {showCreateForm && (
          <div className="p-4 border-b border-border bg-background">
            <div className="space-y-3">
              <input
                type="text"
                placeholder={t('documentGroupSidebar.enterGroupName')}
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
                  {t('documentGroupSidebar.cancel')}
                </Button>
                <Button
                  size="sm"
                  onClick={handleCreateGroup}
                  disabled={!newGroupName.trim()}
                  className="text-xs"
                >
                  {t('documentGroupSidebar.create')}
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="p-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
            <input
              type="text"
              placeholder={t('documentGroupSidebar.searchGroups')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 border border-border rounded-md focus:ring-2 focus:ring-primary focus:border-transparent text-xs bg-background text-text-primary placeholder:text-text-secondary"
            />
          </div>
        </div>

        {error && (
          <div className="mx-4 mt-2 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
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
                    {t('documentGroupSidebar.allDocuments')}
                  </div>
                  <div className="text-xs text-text-secondary">
                    {t('documentGroupSidebar.viewAllDocuments')}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="text-center py-8">
              <div className="text-text-secondary text-sm">{t('documentGroupSidebar.loadingGroups')}</div>
            </div>
          ) : filteredGroups.length === 0 ? (
            <div className="text-center py-8">
              <FolderOpen className="h-12 w-12 text-muted-foreground/20 mx-auto mb-4" />
              <p className="text-text-secondary text-sm">
                {searchQuery ? t('documentGroupSidebar.noGroupsFound') : t('documentGroupSidebar.noGroupsYet')}
              </p>
              {!searchQuery && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCreateForm(true)}
                  className="mt-2"
                >
                  {t('documentGroupSidebar.createFirstGroup')}
                </Button>
              )}
            </div>
          ) : (
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
                    text: t('documentGroupSidebar.documentCount', { count: group.document_count })
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
          )}
        </div>
      </div>

      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title={t('documentGroupSidebar.deleteFolder')}
        description={t('documentGroupSidebar.deleteFolderConfirmation')}
        itemName={groupToDelete?.name}
        itemType="item"
        isLoading={isDeleting}
      />
    </>
  );
};
