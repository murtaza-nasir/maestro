import React from 'react';
import { 
  ClipboardList,  // Planning
  Search,         // Research
  PenTool,        // Writing
  Brain,          // Reflection
  MessageSquare,  // Messenger
  User,           // User
  Settings,       // Controller
  FileEdit,       // Assignment
  Bot             // Default/Unknown
} from 'lucide-react';

export const getAgentIcon = (agentName: string, className: string = "h-4 w-4") => {
  const name = agentName.toLowerCase();
  
  if (name.includes('planning')) {
    return <ClipboardList className={className} />;
  }
  if (name.includes('research')) {
    return <Search className={className} />;
  }
  if (name.includes('writing')) {
    return <PenTool className={className} />;
  }
  if (name.includes('reflection')) {
    return <Brain className={className} />;
  }
  if (name.includes('messenger')) {
    return <MessageSquare className={className} />;
  }
  if (name.includes('user')) {
    return <User className={className} />;
  }
  if (name.includes('controller')) {
    return <Settings className={className} />;
  }
  if (name.includes('assignment')) {
    return <FileEdit className={className} />;
  }
  
  // Default icon for unknown agents
  return <Bot className={className} />;
};

// Get agent color scheme for consistent theming
export const getAgentColorClass = (agentName: string) => {
  const name = agentName.toLowerCase();
  
  if (name.includes('planning')) {
    return 'text-blue-500';
  }
  if (name.includes('research')) {
    return 'text-purple-500';
  }
  if (name.includes('writing')) {
    return 'text-green-500';
  }
  if (name.includes('reflection')) {
    return 'text-orange-500';
  }
  if (name.includes('messenger')) {
    return 'text-cyan-500';
  }
  if (name.includes('user')) {
    return 'text-gray-500';
  }
  if (name.includes('controller')) {
    return 'text-slate-500';
  }
  if (name.includes('assignment')) {
    return 'text-indigo-500';
  }
  
  return 'text-muted-foreground';
};