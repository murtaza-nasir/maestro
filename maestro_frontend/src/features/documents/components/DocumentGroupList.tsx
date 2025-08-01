import React, { useState, useEffect } from 'react';
import { getDocumentGroups, createDocumentGroup, renameDocumentGroup, deleteDocumentGroup } from '../api';
import type { DocumentGroup } from '../types';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import RenameGroupModal from './RenameGroupModal';

interface DocumentGroupListProps {
  onSelectGroup: (group: DocumentGroup) => void;
}

const DocumentGroupList: React.FC<DocumentGroupListProps> = ({ onSelectGroup }) => {
  const [documentGroups, setDocumentGroups] = useState<DocumentGroup[]>([]);
  const [newGroupName, setNewGroupName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renamingGroup, setRenamingGroup] = useState<DocumentGroup | null>(null);

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      setLoading(true);
      const groups = await getDocumentGroups();
      setDocumentGroups(groups);
      setError(null);
    } catch (err) {
      setError('Failed to fetch document groups.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;
    try {
      const newGroup = await createDocumentGroup(newGroupName);
      setNewGroupName('');
      await fetchGroups();
      // Automatically select the newly created group
      onSelectGroup(newGroup);
    } catch (err) {
      setError('Failed to create document group.');
      console.error(err);
    }
  };

  const handleDeleteGroup = async (id: string) => {
    try {
      await deleteDocumentGroup(id);
      fetchGroups();
    } catch (err) {
      setError('Failed to delete document group.');
      console.error(err);
    }
  };

  const handleRenameGroup = async (newName: string) => {
    if (!renamingGroup) return;
    try {
      await renameDocumentGroup(renamingGroup.id, newName);
      setRenamingGroup(null);
      fetchGroups();
    } catch (err) {
      setError('Failed to rename document group.');
      console.error(err);
    }
  };

  return (
    <div className="p-4 bg-background text-text-primary">
      {renamingGroup && (
        <RenameGroupModal
          groupName={renamingGroup.name}
          onRename={handleRenameGroup}
          onCancel={() => setRenamingGroup(null)}
        />
      )}
      <div className="flex mb-4">
        <Input
          type="text"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          placeholder="New group name"
          className="mr-2 bg-background-alt border-border placeholder:text-text-secondary"
        />
        <Button onClick={handleCreateGroup}>Create</Button>
      </div>
      {loading && <p className="text-text-secondary">Loading...</p>}
      {error && <p className="text-destructive">{error}</p>}
      <ul>
        {documentGroups.map((group) => (
          <li key={group.id} className="flex justify-between items-center p-2 border-b border-border cursor-pointer hover:bg-muted" onClick={() => onSelectGroup(group)}>
            <span>{group.name}</span>
            <div>
              <Button variant="ghost" size="sm" className="mr-2 text-text-secondary hover:text-text-primary" onClick={(e) => { e.stopPropagation(); setRenamingGroup(group); }}>Rename</Button>
              <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive/80" onClick={(e) => { e.stopPropagation(); handleDeleteGroup(group.id); }}>Delete</Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default DocumentGroupList;
