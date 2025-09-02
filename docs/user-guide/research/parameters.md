# Research Parameters Reference

This page provides a comprehensive guide to all configurable research parameters in MAESTRO. These settings control how research missions operate, from initial exploration to final report generation.

## Parameter Categories

### 1. Initial Research Phase

Parameters controlling the exploratory phase where MAESTRO investigates your topic broadly.

#### initial_research_max_depth
- **Type**: Integer
- **Default**: 2
- **Range**: 1-5
- **Description**: Maximum depth of the question exploration tree. Higher values create more detailed initial exploration but take longer.
- **When to adjust**: Increase for complex topics requiring thorough initial understanding. Decrease for focused, well-defined topics.

#### initial_research_max_questions
- **Type**: Integer
- **Default**: 10
- **Range**: 5-20
- **Description**: Maximum total questions to explore during initial research phase.
- **When to adjust**: Increase for broad topics requiring extensive exploration. Decrease for time-sensitive research.

#### initial_exploration_doc_results
- **Type**: Integer
- **Default**: 5
- **Range**: 3-10
- **Description**: Number of document results to retrieve per query during initial exploration.
- **When to adjust**: Increase when you have a large, relevant document library. Decrease to reduce processing time.

#### initial_exploration_web_results
- **Type**: Integer
- **Default**: 2
- **Range**: 0-5
- **Description**: Number of web search results to retrieve per query during initial exploration.
- **When to adjust**: Increase for current events or rapidly evolving topics. Set to 0 for purely document-based research.

### 2. Structured Research Phase

Parameters controlling the main research phase where MAESTRO systematically investigates each section.

#### structured_research_rounds
- **Type**: Integer
- **Default**: 2
- **Range**: 1-5
- **Description**: Number of complete research rounds through the outline. Each round deepens the investigation.
- **When to adjust**: Increase for comprehensive academic research. Keep low for quick overviews.

#### main_research_doc_results
- **Type**: Integer
- **Default**: 5
- **Range**: 3-20
- **Description**: Number of document results per query during main research phase.
- **When to adjust**: Increase when documents are your primary source. Balance with web results for comprehensive coverage.

#### main_research_web_results
- **Type**: Integer
- **Default**: 5
- **Range**: 0-20
- **Description**: Number of web results per query during main research phase.
- **When to adjust**: Increase for current topics or when document library is limited. Set to 0 for confidential research.

#### max_research_cycles_per_section
- **Type**: Integer
- **Default**: 2
- **Range**: 1-3
- **Description**: Maximum research iterations for each outline section. Controls depth of investigation per topic.
- **When to adjust**: Increase for sections requiring deep analysis. Keep at 1 for time-sensitive research.

### 3. Writing Phase

Parameters controlling report generation and refinement.

#### writing_passes
- **Type**: Integer
- **Default**: 2
- **Range**: 1-5
- **Description**: Number of writing iterations (initial draft + revisions). Each pass refines and improves the content.
- **When to adjust**: Increase for publication-quality output. Decrease for quick drafts or when time is critical.

#### writing_previous_content_preview_chars
- **Type**: Integer
- **Default**: 30,000
- **Range**: 10,000-50,000
- **Description**: Characters of previous sections shown to maintain consistency during writing.
- **When to adjust**: Increase for highly interconnected content. Decrease to reduce context usage and costs.

#### writing_agent_max_context_chars
- **Type**: Integer
- **Default**: 300,000
- **Range**: 100,000-500,000
- **Description**: Maximum total context size for writing agent (includes notes, outline, and previous content).
- **When to adjust**: Increase for complex reports with extensive notes. Decrease if hitting model context limits.

### 4. Writing Mode Search (Interactive Writing)

Parameters for when using search during interactive writing sessions.

#### writing_search_max_iterations
- **Type**: Integer
- **Default**: 1
- **Range**: 1-3
- **Description**: Search iterations for standard writing mode queries.
- **When to adjust**: Increase when writing requires extensive fact-checking.

#### writing_search_max_queries
- **Type**: Integer
- **Default**: 3
- **Range**: 1-5
- **Description**: Number of queries per writing mode search iteration.
- **When to adjust**: Increase for complex topics requiring multiple perspectives.

#### writing_deep_search_iterations
- **Type**: Integer
- **Default**: 3
- **Range**: 2-5
- **Description**: Search iterations when "deep search" is enabled in writing mode.
- **When to adjust**: Use for critical sections requiring thorough research.

#### writing_deep_search_queries
- **Type**: Integer
- **Default**: 5
- **Range**: 3-10
- **Description**: Queries per iteration during deep search in writing mode.
- **When to adjust**: Increase for comprehensive background research during writing.

#### writing_mode_doc_results
- **Type**: Integer
- **Default**: 5
- **Range**: 3-10
- **Description**: Document results per query in writing mode searches.
- **When to adjust**: Match to your document library size and relevance.

#### writing_mode_web_results
- **Type**: Integer
- **Default**: 5
- **Range**: 3-10
- **Description**: Web results per query in writing mode searches.
- **When to adjust**: Increase for fact-checking and current information needs.

### 5. Note Management

Parameters controlling how research notes are organized and assigned to sections.

#### max_notes_for_assignment_reranking
- **Type**: Integer
- **Default**: 30
- **Range**: 10-150
- **Description**: Maximum notes to keep per section after reranking during section assignment.
- **When to adjust**: Increase for more note relevant content per section at the cost of processing time.

#### min_notes_per_section_assignment
- **Type**: Integer
- **Default**: 5
- **Range**: 3-10
- **Description**: Minimum notes assigned to each section to ensure adequate coverage.
- **When to adjust**: Increase for detailed sections. Decrease for overview-style reports.

#### max_notes_per_section_assignment
- **Type**: Integer
- **Default**: 40
- **Range**: 20-60
- **Description**: Maximum notes per section during research rounds. Will stop after this limit is reached.
- **When to adjust**: Increase for comprehensive sections. Decrease for concise reports.

#### research_note_content_limit
- **Type**: Integer
- **Default**: 32,000
- **Range**: 16,000-64,000
- **Description**: Maximum characters per research note.
- **When to adjust**: Increase to capture more context per note. Decrease to create more granular notes.

### 6. Performance and Optimization

Parameters affecting speed, cost, and system behavior.

#### max_concurrent_requests
- **Type**: Integer
- **Default**: 25
- **Minimum**: 10 (enforced to prevent deadlocks)
- **Range**: 10-50
- **Description**: Maximum concurrent API requests to LLM providers.
- **When to adjust**: Increase for faster processing (higher cost). Decrease to stay within rate limits.

#### thought_pad_context_limit
- **Type**: Integer
- **Default**: 10
- **Range**: 5-20
- **Description**: Number of recent thoughts/decisions to maintain in agent memory.
- **When to adjust**: Increase for complex decision tracking. Decrease to reduce context usage.

#### max_planning_context_chars
- **Type**: Integer
- **Default**: 250,000
- **Range**: 100,000-400,000
- **Description**: Maximum context size for planning operations.
- **When to adjust**: Increase for complex outlines. Decrease if hitting model limits.

#### skip_final_replanning
- **Type**: Boolean
- **Default**: false
- **Description**: Skip the final outline optimization step to save time.
- **When to adjust**: Enable for time-critical research or when initial outline is satisfactory.

#### auto_optimize_params
- **Type**: Boolean
- **Default**: false
- **Description**: Automatically adjust parameters based on topic analysis.
- **When to adjust**: Enable for hands-off operation. Disable for precise control.

### 7. Advanced Loop Control

Parameters for fine-tuning research iteration behavior.

#### max_total_iterations
- **Type**: Integer
- **Default**: 40
- **Range**: 20-100
- **Description**: Global limit on total research iterations across all sections.
- **When to adjust**: Increase for exhaustive research. Decrease to control costs and time.

#### max_total_depth
- **Type**: Integer
- **Default**: 2
- **Range**: 1-4
- **Description**: Maximum depth for hierarchical research exploration. Determines maximum depth of generated outline structure.
- **When to adjust**: Increase for multi-layered topics. Keep low for flat, straightforward subjects.

#### max_suggestions_per_batch
- **Type**: Integer
- **Default**: 3
- **Range**: 1-10 (-1 for unlimited)
- **Description**: Parent sections to process per batch during outline revision.
- **When to adjust**: Increase for faster processing. Decrease if hitting model context limits.

## Presets and Templates

### Quick Research
Best for: Rapid overviews, time-sensitive reports
```
initial_research_max_depth: 1
initial_research_max_questions: 5
structured_research_rounds: 1
writing_passes: 2
max_concurrent_requests: 20
```

### Standard Research
Best for: Balanced depth and speed
```
initial_research_max_depth: 2
initial_research_max_questions: 10
structured_research_rounds: 2
writing_passes: 3
max_concurrent_requests: 10
```

### Deep Research
Best for: Comprehensive investigations, academic papers
```
initial_research_max_depth: 3
initial_research_max_questions: 15
structured_research_rounds: 3
writing_passes: 4
max_concurrent_requests: 15
max_research_cycles_per_section: 3
```

### Document-Focused
Best for: Research primarily from uploaded documents
```
initial_exploration_doc_results: 8
initial_exploration_web_results: 0
main_research_doc_results: 10
main_research_web_results: 0
```

### Web-Focused
Best for: Current events, trending topics
```
initial_exploration_doc_results: 2
initial_exploration_web_results: 5
main_research_doc_results: 3
main_research_web_results: 10
```

## Settings Precedence

Parameters can be configured at multiple levels, with the following precedence (highest to lowest):

1. **Mission-specific settings** - Set when starting a mission
2. **User settings** - Configured in Settings → Research tab
3. **System defaults** - Built-in fallback values

## Performance Impact

### High Impact on Speed
- `max_concurrent_requests` - Direct multiplier on processing speed
- `structured_research_rounds` - Linear impact on total time
- `initial_research_max_questions` - Affects initial phase duration
- `writing_passes` - Each pass adds significant time

### High Impact on Cost
- `main_research_web_results` - More results = more API calls
- `structured_research_rounds` - Linear impact on API calls
- `main_research_doc_results` - More embeddings and processing
- `max_concurrent_requests` - Higher concurrency = higher peak usage
- `writing_passes` - Multiple rewrites increase token usage

### High Impact on Quality
- `structured_research_rounds` - More rounds = deeper insights
- `writing_passes` - More passes = better coherence
- `max_notes_per_section_assignment` - More notes = richer content
- `max_research_cycles_per_section` - More cycles = thorough coverage

## Tips for Optimization

1. **Start with defaults** - The default values work well for most use cases
2. **Adjust incrementally** - Change one parameter at a time to understand impact
3. **Monitor costs** - Watch the statistics tab during research
4. **Consider your sources** - Balance document vs web based on your library
5. **Time vs Quality** - There's always a trade-off; be clear about priorities

## Related Documentation

- [Research Overview](overview.md) - Understanding the research workflow
- [AI Configuration](../settings/ai-config.md) - Model selection impacts
- [Performance Tuning](../../troubleshooting/common-issues/installation.md) - System optimization