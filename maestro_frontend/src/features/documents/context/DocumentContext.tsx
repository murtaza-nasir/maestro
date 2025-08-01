import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { DocumentGroup } from '../types';

interface DocumentContextType {
  selectedGroup: DocumentGroup | null;
  setSelectedGroup: (group: DocumentGroup | null) => void;
  refreshGroups: () => void;
  groupsRefreshKey: number;
}

const DocumentContext = createContext<DocumentContextType | undefined>(undefined);

export const useDocumentContext = () => {
  const context = useContext(DocumentContext);
  if (context === undefined) {
    throw new Error('useDocumentContext must be used within a DocumentProvider');
  }
  return context;
};

interface DocumentProviderProps {
  children: ReactNode;
}

export const DocumentProvider: React.FC<DocumentProviderProps> = ({ children }) => {
  const [selectedGroup, setSelectedGroup] = useState<DocumentGroup | null>(null);
  const [groupsRefreshKey, setGroupsRefreshKey] = useState(0);

  const refreshGroups = () => {
    setGroupsRefreshKey(prev => prev + 1);
  };

  return (
    <DocumentContext.Provider value={{ 
      selectedGroup, 
      setSelectedGroup, 
      refreshGroups, 
      groupsRefreshKey 
    }}>
      {children}
    </DocumentContext.Provider>
  );
};
