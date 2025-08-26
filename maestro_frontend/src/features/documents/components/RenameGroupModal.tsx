import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';

interface RenameGroupModalProps {
  groupName: string;
  onRename: (newName: string) => void;
  onCancel: () => void;
}

const RenameGroupModal: React.FC<RenameGroupModalProps> = ({ groupName, onRename, onCancel }) => {
  const { t } = useTranslation();
  const [newName, setNewName] = useState(groupName);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onRename(newName);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-background p-6 rounded-lg shadow-xl border border-border">
        <h2 className="text-lg font-bold mb-4 text-text-primary">{t('renameGroupModal.title')}</h2>
        <form onSubmit={handleSubmit}>
          <Input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="mb-4 bg-background-alt border-border placeholder:text-text-secondary"
          />
          <div className="flex justify-end">
            <Button type="button" variant="ghost" onClick={onCancel} className="mr-2">
              {t('renameGroupModal.cancel')}
            </Button>
            <Button type="submit">{t('renameGroupModal.rename')}</Button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RenameGroupModal;
