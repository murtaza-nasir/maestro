# Agent Activity Log Visualization System

This directory contains a comprehensive visualization system for displaying agent activity logs in the MAESTRO research application. The system provides rich, user-friendly representations of different agent types and their outputs.

## Architecture Overview

### Agent Types and Their Outputs

Based on the provided log data, the system handles several types of agents:

#### 1. ResearchAgent
**Purpose**: Conducts research by exploring questions, searching the web, and gathering information.

**Key Outputs**:
- **Tool Calls**: Web searches, page fetching, file interactions
- **Question Exploration**: Relevant notes found, new sub-questions generated, updated scratchpad
- **Model Performance**: Token usage, cost, duration
- **File Interactions**: List of files accessed or modified

**Visualization Features**:
- Tool calls with icons (🌐 for web search, 🔗 for page fetching, 📄 for files)
- Question exploration with brain icon showing research progress
- Expandable tool arguments and results
- Model performance metrics in a grid layout

#### 2. PlanningAgent
**Purpose**: Creates research plans, defines objectives, and sets success criteria.

**Key Outputs**:
- **Research Questions**: List of questions to investigate
- **Plan Steps**: Ordered list of execution steps
- **Timeline**: Estimated completion timeline
- **Success Criteria**: Metrics for measuring success

**Visualization Features**:
- Structured display of planning outputs with appropriate icons
- Timeline visualization
- Success criteria as highlighted items

#### 3. WritingAgent
**Purpose**: Generates written content, reports, and documentation.

**Key Outputs**:
- **Content Preview**: Sample of generated text
- **Word Count**: Length metrics
- **Sections Written**: List of completed sections
- **Quality Metrics**: Writing quality assessments
- **Sources Used**: Referenced materials

**Visualization Features**:
- Content preview with proper formatting
- Writing metrics dashboard
- Quality indicators
- Source tracking

#### 4. Other Agents (Controller, Messenger, etc.)
**Purpose**: Various system and coordination tasks.

**Outputs**: Generic tool calls, input/output summaries, model details.

**Visualization**: Default renderer with tool calls and raw data access.

## Component Structure

### Core Components

#### `AgentActivityLog.tsx`
Main orchestrator component that:
- Manages log state and expansion
- Routes logs to appropriate renderers based on agent type
- Handles auto-scrolling and loading states
- Provides overall layout and header

#### `LogEntryCard.tsx`
Wrapper component for individual log entries that:
- Displays agent icon, name, timestamp, and status
- Shows model performance badges
- Handles expand/collapse functionality
- Provides consistent styling with status-based border colors

#### Agent-Specific Renderers

##### `ResearchAgentLog.tsx`
- **Tool Calls Section**: Displays web searches, page fetches with icons and status
- **Question Exploration**: Shows research progress and sub-questions
- **Model Details**: Performance metrics grid
- **File Interactions**: List of accessed files

##### `PlanningAgentLog.tsx`
- **Planning Output**: Research questions, plan steps, timeline
- **Success Criteria**: Goal definitions
- **Model Performance**: Standard metrics

##### `WritingAgentLog.tsx`
- **Writing Output**: Content preview, word count, sections
- **Quality Metrics**: Writing assessment data
- **Sources**: Referenced materials

##### `DefaultLogRenderer.tsx`
- **Generic Display**: Input/output summaries, tool calls
- **Raw Data Access**: Collapsible JSON viewers
- **Model Performance**: Standard metrics

## Data Flow

### Log Entry Structure
```typescript
interface ExecutionLogEntry {
  timestamp: string;
  agent_name: string;
  action: string;
  input_summary?: string;
  output_summary?: string;
  status: 'success' | 'failure' | 'warning' | 'running';
  error_message?: string;
  full_input?: any;
  full_output?: any;
  model_details?: {
    provider?: string;
    model_name?: string;
    duration_sec?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    cost?: number;
  };
  tool_calls?: Array<{
    tool_name: string;
    arguments: any;
    result_summary: string;
    error?: string;
  }>;
  file_interactions?: string[];
}
```

### WebSocket Integration
The system receives real-time updates via WebSocket messages:
- Listens for `logs_update` messages
- Automatically appends new logs
- Maintains scroll position at bottom for new entries
- Updates mission store for persistence

### State Management
- **Local State**: Expanded log entries, loading status
- **Mission Store**: Persistent log storage across sessions
- **Auto-scroll**: Keeps latest entries visible

## Visual Design

### Status Indicators
- **Success**: Green checkmark ✅
- **Failure**: Red alert circle ❌
- **Running**: Blue pulsing activity icon 🔄
- **Warning**: Yellow alert triangle ⚠️

### Agent Icons
- **Research**: 🔍 (magnifying glass)
- **Planning**: 📋 (clipboard)
- **Writing**: ✍️ (writing hand)
- **Controller**: ⚙️ (gear)
- **Messenger**: 💬 (speech bubble)
- **Default**: 🤖 (robot)

### Color Coding
- **Border Colors**: Status-based left border (green/red/blue/yellow)
- **Background**: White cards with gray backgrounds for expanded content
- **Text**: Hierarchical gray scale for information priority
- **Badges**: Colored backgrounds for status and metrics

## Usage Examples

### Basic Integration
```tsx
import { AgentActivityLog } from '../../../components/mission';

<AgentActivityLog 
  logs={executionLogs}
  isLoading={false}
  missionStatus="running"
/>
```

### Custom Log Processing
```tsx
// Transform backend logs to frontend format
const processedLogs = rawLogs.map(log => ({
  ...log,
  timestamp: log.timestamp || new Date().toISOString(),
  // Add any additional processing
}));
```

## Performance Considerations

### Optimization Features
- **Lazy Rendering**: Expanded content only renders when needed
- **Virtualization Ready**: Structure supports virtual scrolling for large datasets
- **Memoization**: Components use React.memo where appropriate
- **Efficient Updates**: Only re-renders changed log entries

### Memory Management
- **Collapsible Raw Data**: Large JSON objects hidden by default
- **Truncated Previews**: Long text content is truncated with expand options
- **Selective Rendering**: Only visible content is fully processed

## Extensibility

### Adding New Agent Types
1. Create new renderer component following existing patterns
2. Add agent detection logic in `AgentActivityLog.tsx`
3. Export from `index.ts`
4. Add appropriate icons and styling

### Custom Visualizations
- Each renderer can implement custom visualization logic
- Shared utilities available for common patterns
- Consistent styling through Tailwind classes

## Testing Considerations

### Test Data Structure
The system expects logs with the structure shown in the provided example data, including:
- ResearchAgent logs with tool_calls and full_output.relevant_notes
- Model details with performance metrics
- Proper timestamp formatting
- Status indicators

### Error Handling
- Graceful degradation for missing data fields
- Error boundaries for malformed log entries
- Fallback to default renderer for unknown agent types
