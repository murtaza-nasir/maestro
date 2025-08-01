export interface ParsedAction {
  type: 'explore_question' | 'research_section' | 'execute_tool' | 'generate_outline' | 
        'revise_outline' | 'write_section' | 'synthesize_intro' | 'reflect_section' | 'unknown';
  metadata: {
    depth?: number;
    section_id?: string;
    pass?: number;
    cycle?: number;
    batch?: number;
    tool_name?: string;
    question?: string;
  };
  phase?: 'initial_research' | 'structured_research' | 'writing' | 'reflection';
}

export class ActionParser {
  static parseAction(action: string, agentName: string): ParsedAction {
    // Add null/undefined checks to prevent crashes
    if (!action || typeof action !== 'string') {
      return {
        type: 'unknown',
        metadata: {},
        phase: undefined
      };
    }
    
    if (!agentName || typeof agentName !== 'string') {
      return {
        type: 'unknown',
        metadata: {},
        phase: undefined
      };
    }

    // const lowerAction = action.toLowerCase();
    const agentType = agentName.toLowerCase();

    // Research Agent patterns
    if (agentType.includes('research')) {
      // Explore Question (Depth X)
      const exploreMatch = action.match(/explore question.*depth (\d+)/i);
      if (exploreMatch) {
        return {
          type: 'explore_question',
          metadata: { depth: parseInt(exploreMatch[1]) },
          phase: 'initial_research'
        };
      }

      // Research Section: {section_id} (Pass X, Cycle Y)
      const sectionMatch = action.match(/research section:\s*([^(]+)\s*\(pass (\d+),?\s*cycle (\d+)\)/i);
      if (sectionMatch) {
        return {
          type: 'research_section',
          metadata: {
            section_id: sectionMatch[1].trim(),
            pass: parseInt(sectionMatch[2]),
            cycle: parseInt(sectionMatch[3])
          },
          phase: 'structured_research'
        };
      }

      // Execute Tool: {tool_name}
      const toolMatch = action.match(/execute tool:\s*(.+)/i);
      if (toolMatch) {
        return {
          type: 'execute_tool',
          metadata: { tool_name: toolMatch[1].trim() },
          phase: undefined
        };
      }
    }

    // Planning Agent patterns
    if (agentType.includes('planning')) {
      // Generate Preliminary Outline (Batch X)
      const generateMatch = action.match(/generate preliminary outline.*batch (\d+)/i);
      if (generateMatch) {
        return {
          type: 'generate_outline',
          metadata: { batch: parseInt(generateMatch[1]) },
          phase: 'initial_research'
        };
      }

      // Revise Outline (Batch X)
      const reviseMatch = action.match(/revise outline.*batch (\d+)/i);
      if (reviseMatch) {
        return {
          type: 'revise_outline',
          metadata: { batch: parseInt(reviseMatch[1]) },
          phase: 'structured_research'
        };
      }
    }

    // Writing Agent patterns
    if (agentType.includes('writing')) {
      // Write Section: {section_id}
      const writeMatch = action.match(/write section:\s*(.+)/i);
      if (writeMatch) {
        return {
          type: 'write_section',
          metadata: { section_id: writeMatch[1].trim() },
          phase: 'writing'
        };
      }

      // Synthesize Intro for Section: {section_id}
      const synthMatch = action.match(/synthesize intro for section:\s*(.+)/i);
      if (synthMatch) {
        return {
          type: 'synthesize_intro',
          metadata: { section_id: synthMatch[1].trim() },
          phase: 'writing'
        };
      }
    }

    // Reflection Agent patterns
    if (agentType.includes('reflection')) {
      // Reflect on Section: {section_id} (Pass X)
      const reflectMatch = action.match(/reflect on section:\s*([^(]+)\s*\(pass (\d+)\)/i);
      if (reflectMatch) {
        return {
          type: 'reflect_section',
          metadata: {
            section_id: reflectMatch[1].trim(),
            pass: parseInt(reflectMatch[2])
          },
          phase: 'reflection'
        };
      }
    }

    return {
      type: 'unknown',
      metadata: {},
      phase: undefined
    };
  }

  static getActionIcon(parsedAction: ParsedAction): string {
    switch (parsedAction.type) {
      case 'explore_question':
        return '🔍';
      case 'research_section':
        return '📚';
      case 'execute_tool':
        return '🔧';
      case 'generate_outline':
        return '📋';
      case 'revise_outline':
        return '✏️';
      case 'write_section':
        return '✍️';
      case 'synthesize_intro':
        return '🔗';
      case 'reflect_section':
        return '🤔';
      default:
        return '⚡';
    }
  }

  static getActionDescription(parsedAction: ParsedAction): string {
    const { type, metadata } = parsedAction;
    
    switch (type) {
      case 'explore_question':
        return `Exploring research question at depth ${metadata.depth}`;
      case 'research_section':
        return `Researching "${metadata.section_id}" (Pass ${metadata.pass}, Cycle ${metadata.cycle})`;
      case 'execute_tool':
        return `Using ${metadata.tool_name} tool`;
      case 'generate_outline':
        return `Generating preliminary outline (Batch ${metadata.batch})`;
      case 'revise_outline':
        return `Revising outline structure (Batch ${metadata.batch})`;
      case 'write_section':
        return `Writing section: "${metadata.section_id}"`;
      case 'synthesize_intro':
        return `Synthesizing introduction for "${metadata.section_id}"`;
      case 'reflect_section':
        return `Reflecting on "${metadata.section_id}" (Pass ${metadata.pass})`;
      default:
        return 'Processing...';
    }
  }

  static getPhaseColor(phase?: string): string {
    switch (phase) {
      case 'initial_research':
        return 'bg-blue-100 text-blue-800';
      case 'structured_research':
        return 'bg-purple-100 text-purple-800';
      case 'writing':
        return 'bg-green-100 text-green-800';
      case 'reflection':
        return 'bg-orange-100 text-orange-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }
}
