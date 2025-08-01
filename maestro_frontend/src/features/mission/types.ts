export interface GoalEntry {
  goal_id: string;
  text: string;
  status: 'active' | 'addressed' | 'obsolete';
  source_agent?: string;
}

export interface ThoughtEntry {
  thought_id: string;
  agent_name: string;
  content: string;
}

export interface MissionContext {
  goal_pad: GoalEntry[];
  thought_pad: ThoughtEntry[];
  agent_scratchpad: string | null;
}
