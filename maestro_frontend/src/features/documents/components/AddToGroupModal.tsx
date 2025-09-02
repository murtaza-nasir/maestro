import React, { useState, useEffect } from 'react';
import { X, Plus, FolderPlus } from 'lucide-react';
import { getDocumentGroups, createDocumentGroup, bulkAddDocumentsToGroup } from '../api';
import type { DocumentGroupWithCount } from '../types';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';

interface AddToGroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedDocumentIds: string[];
  onSuccess: () => void;
}

export const AddToGroupModal: React.FC<AddToGroupModalProps> = ({
  isOpen,
  onClose,
  selectedDocumentIds,
  onSuccess
}) => {
  const [groups, setGroups] = useState<DocumentGroupWithCount[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [showNewGroupInput, setShowNewGroupInput] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadGroups();
    }
  }, [isOpen]);

  const loadGroups = async () => {
    try {
      const groupList = await getDocumentGroups();
      setGroups(groupList);
    } catch (err) {
      console.error('Failed to load groups:', err);
      setError('Failed to load document groups');
    }
  };

  const handleAddToGroup = async () => {
    if (!selectedGroupId && !newGroupName.trim()) {
      setError('Please select a group or create a new one');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      let groupId = selectedGroupId;

      // Create new group if needed
      if (!groupId && newGroupName.trim()) {
        const newGroup = await createDocumentGroup(newGroupName.trim());
        groupId = newGroup.id;
      }

      if (groupId) {
        // Add documents to the group
        await bulkAddDocumentsToGroup(groupId, selectedDocumentIds);
        onSuccess();
        onClose();
      }
    } catch (err) {
      console.error('Failed to add documents to group:', err);
      setError('Failed to add documents to group');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setSelectedGroupId(null);
    setShowNewGroupInput(false);
    setNewGroupName('');
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 max-w-md w-full max-h-[80vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">
            Add {selectedDocumentIds.length} document{selectedDocumentIds.length !== 1 ? 's' : ''} to group
          </h2>
          <button
            onClick={handleClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        <div className="flex-1 overflow-y-auto mb-4">
          {/* Create New Group Option */}
          <button
            onClick={() => {
              setShowNewGroupInput(!showNewGroupInput);
              setSelectedGroupId(null);
            }}
            className="w-full p-3 mb-2 border border-border rounded-md hover:bg-muted/50 flex items-center gap-2 text-left"
          >
            <FolderPlus className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">Create new group</span>
          </button>

          {showNewGroupInput && (
            <div className="mb-4 p-3 bg-muted/50 rounded-md">
              <Input
                type="text"
                placeholder="New group name..."
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                className="mb-2"
                autoFocus
              />
            </div>
          )}

          {/* Existing Groups */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Or select existing group:</h3>
            {groups.map((group) => (
              <button
                key={group.id}
                onClick={() => {
                  setSelectedGroupId(group.id);
                  setShowNewGroupInput(false);
                  setNewGroupName('');
                }}
                className={`w-full p-3 border rounded-md text-left transition-colors ${
                  selectedGroupId === group.id
                    ? 'border-primary bg-primary/10'
                    : 'border-border hover:bg-muted/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{group.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {group.document_count} document{group.document_count !== 1 ? 's' : ''}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
            className="flex-1"
          >
            Cancel
          </Button>
          <Button
            onClick={handleAddToGroup}
            disabled={isLoading || (!selectedGroupId && !newGroupName.trim())}
            className="flex-1"
          >
            {isLoading ? (
              'Adding...'
            ) : (
              <>
                <Plus className="h-4 w-4 mr-2" />
                Add to Group
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};