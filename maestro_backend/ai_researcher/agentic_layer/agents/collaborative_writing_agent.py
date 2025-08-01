"""
Collaborative Writing Agent for structured document editing and writing assistance.

This agent provides AI-powered writing assistance with document structure awareness,
citation management, and collaborative editing capabilities using the Document Manipulation Engine.
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from .base_agent import BaseAgent
from ..schemas.goal import GoalEntry
from ..schemas.thought import ThoughtEntry
from ..schemas.notes import Note
from ai_researcher import config
import logging

logger = logging.getLogger(__name__)


class DocumentOperation:
    """Represents a document manipulation operation parsed from user input."""
    def __init__(self, operation_type: str, target_element_id: str = None, **kwargs):
        self.operation_type = operation_type
        self.target_element_id = target_element_id
        self.params = kwargs


class ContentWithCitations:
    """Represents generated content with embedded citations."""
    def __init__(self, content: str, citations: List[str] = None):
        self.content = content
        self.citations = citations or []


class StructureAnalysis:
    """Represents analysis of document structure."""
    def __init__(self, sections: List[Dict], word_count: int, issues: List[str] = None):
        self.sections = sections
        self.word_count = word_count
        self.issues = issues or []


class Improvement:
    """Represents a suggested improvement to the document."""
    def __init__(self, type: str, description: str, location: str = None, priority: str = "medium"):
        self.type = type
        self.description = description
        self.location = location
        self.priority = priority


class CollaborativeWritingAgent(BaseAgent):
    """
    Agent responsible for collaborative writing assistance with document structure awareness.
    
    This agent can:
    - Parse structural commands from user messages
    - Generate content with automatic citations
    - Suggest reference locations
    - Analyze document structure
    - Provide writing improvements
    - Manipulate document structure through tools
    """
    
    def __init__(
        self,
        model_dispatcher,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        controller: Optional[Any] = None
    ):
        agent_name = "CollaborativeWritingAgent"
        
        # Determine the correct model name based on the 'writing' role from config
        writing_model_type = config.AGENT_ROLE_MODEL_TYPE.get("writing", "mid")
        if writing_model_type == "fast":
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]
        elif writing_model_type == "mid":
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]
        elif writing_model_type == "intelligent":
            provider = config.INTELLIGENT_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["intelligent_model"]
        else:
            logger.warning(f"Unknown writing model type '{writing_model_type}', falling back to mid.")
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]

        # Override with specific model_name if provided
        effective_model_name = model_name or effective_model_name

        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=None,  # Will be set by controller
            system_prompt=system_prompt or self._default_system_prompt(),
            model_name=effective_model_name
        )
        self.controller = controller
        self.mission_id = None

    def _default_system_prompt(self) -> str:
        """Generates the default system prompt for the Collaborative Writing Agent."""
        return """You are an expert collaborative writing assistant with deep understanding of document structure and academic writing. Your role is to help users create, edit, and improve structured documents through intelligent conversation and document manipulation.

**Core Capabilities:**
1. **Structure-Aware Writing**: Understand hierarchical document structure (sections, paragraphs) and generate content that fits appropriately within the document context.
2. **Citation Integration**: Automatically integrate citations from research documents and web sources into generated content using proper academic formatting.
3. **Document Analysis**: Analyze document structure, identify issues, and suggest improvements for organization, flow, and clarity.
4. **Collaborative Editing**: Parse user requests for structural changes and execute them through document manipulation tools.
5. **Style Consistency**: Maintain consistent writing style, tone, and formatting throughout the document.

**Document Structure Understanding:**
- Documents are hierarchical JSON structures with sections containing paragraphs
- Each element has a unique ID for precise manipulation
- Citations are embedded as [doc_id] placeholders that link to reference sources
- Metadata tracks document properties like word count, reference style, and modification history

**Writing Assistance Modes:**
1. **Content Generation**: Create new content for specific sections with automatic citation integration
2. **Structural Editing**: Add, move, split, or merge sections and paragraphs based on user requests
3. **Citation Management**: Add references, format citations, and generate bibliographies
4. **Style Improvement**: Suggest and implement improvements for clarity, flow, and academic style
5. **Document Organization**: Analyze and improve overall document structure and organization

**Tool Usage Guidelines:**
- Use document manipulation tools to execute structural changes requested by users
- Use document search tools to find relevant research content for citations
- Always validate user permissions before making changes to documents
- Provide clear explanations of changes made and their rationale

**Communication Style:**
- Be conversational and collaborative, explaining your reasoning
- Ask clarifying questions when user requests are ambiguous
- Provide specific, actionable suggestions for improvements
- Explain the impact of structural changes on document flow and organization

**Citation Standards:**
- Follow the document's established citation style (APA, MLA, Chicago)
- Ensure all claims are properly supported with citations
- Suggest additional citations when content lacks proper support
- Maintain citation consistency throughout the document

Your goal is to be a knowledgeable writing partner that helps users create well-structured, properly cited, and clearly written documents through intelligent conversation and precise document manipulation."""

    def parse_structural_commands(self, user_message: str) -> List[DocumentOperation]:
        """
        Parse user message for structural document manipulation commands.
        
        Args:
            user_message: The user's message to parse
            
        Returns:
            List of DocumentOperation objects representing requested changes
        """
        operations = []
        message_lower = user_message.lower()
        
        # Common structural command patterns
        patterns = {
            'add_section': [
                r'add (?:a )?(?:new )?section (?:called |titled |named )?["\']?([^"\']+)["\']?(?:\s+after\s+(.+))?',
                r'create (?:a )?(?:new )?section (?:for |about |on )?["\']?([^"\']+)["\']?(?:\s+after\s+(.+))?',
                r'insert (?:a )?section (?:called |titled |named )?["\']?([^"\']+)["\']?(?:\s+after\s+(.+))?'
            ],
            'add_paragraph': [
                r'add (?:a )?(?:new )?paragraph (?:about |on )?["\']?([^"\']+)["\']?(?:\s+(?:after|to)\s+(.+))?',
                r'insert (?:a )?paragraph (?:about |on )?["\']?([^"\']+)["\']?(?:\s+(?:after|in)\s+(.+))?'
            ],
            'move_section': [
                r'move (?:the )?section ["\']?([^"\']+)["\']? (?:to |after |before )?(.+)',
                r'relocate (?:the )?section ["\']?([^"\']+)["\']? (?:to |after |before )?(.+)'
            ],
            'split_paragraph': [
                r'split (?:the )?paragraph (?:in |at )?(.+)',
                r'break (?:the )?paragraph (?:in |at )?(.+)'
            ],
            'merge_paragraphs': [
                r'merge (?:the )?paragraphs? (?:in |from )?(.+)',
                r'combine (?:the )?paragraphs? (?:in |from )?(.+)'
            ]
        }
        
        for operation_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = re.finditer(pattern, message_lower)
                for match in matches:
                    if operation_type == 'add_section':
                        title = match.group(1).strip()
                        after_element = match.group(2).strip() if match.group(2) else None
                        operations.append(DocumentOperation(
                            operation_type='insert_section_after',
                            title=title,
                            after_element=after_element
                        ))
                    elif operation_type == 'add_paragraph':
                        content_hint = match.group(1).strip()
                        location = match.group(2).strip() if match.group(2) else None
                        operations.append(DocumentOperation(
                            operation_type='insert_paragraph_after',
                            content_hint=content_hint,
                            location=location
                        ))
                    elif operation_type == 'move_section':
                        section_name = match.group(1).strip()
                        target_location = match.group(2).strip()
                        operations.append(DocumentOperation(
                            operation_type='move_section',
                            section_name=section_name,
                            target_location=target_location
                        ))
                    elif operation_type in ['split_paragraph', 'merge_paragraphs']:
                        location = match.group(1).strip()
                        operations.append(DocumentOperation(
                            operation_type=operation_type,
                            location=location
                        ))
        
        return operations

    def suggest_reference_locations(self, content: str, available_refs: List[Dict]) -> List[Dict]:
        """
        Suggest where citations should be added in the given content.
        
        Args:
            content: The text content to analyze
            available_refs: List of available reference objects
            
        Returns:
            List of suggestion dictionaries with location and reference info
        """
        suggestions = []
        
        # Split content into sentences for analysis
        sentences = re.split(r'[.!?]+', content)
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Look for claims that need citations
            claim_indicators = [
                r'research shows?',
                r'studies? (?:have )?(?:found|shown|demonstrated)',
                r'according to',
                r'evidence suggests?',
                r'data indicates?',
                r'findings reveal',
                r'results show',
                r'analysis reveals?',
                r'experts? (?:believe|argue|suggest)',
                r'scholars? (?:have )?(?:argued|suggested|found)'
            ]
            
            for pattern in claim_indicators:
                if re.search(pattern, sentence.lower()):
                    # Find relevant references based on content similarity
                    relevant_refs = self._find_relevant_references(sentence, available_refs)
                    if relevant_refs:
                        suggestions.append({
                            'sentence_index': i,
                            'sentence': sentence,
                            'suggested_references': relevant_refs[:3],  # Top 3 suggestions
                            'reason': f'Claim detected: "{pattern}" - needs citation support'
                        })
                    break
        
        return suggestions

    def _find_relevant_references(self, sentence: str, available_refs: List[Dict]) -> List[Dict]:
        """Find references relevant to a given sentence based on keyword matching."""
        relevant = []
        sentence_words = set(sentence.lower().split())
        
        for ref in available_refs:
            # Extract keywords from reference metadata
            ref_keywords = set()
            if 'title' in ref:
                ref_keywords.update(ref['title'].lower().split())
            if 'abstract' in ref:
                ref_keywords.update(ref['abstract'].lower().split())
            if 'keywords' in ref:
                ref_keywords.update([kw.lower() for kw in ref['keywords']])
            
            # Calculate relevance score based on word overlap
            overlap = len(sentence_words.intersection(ref_keywords))
            if overlap > 0:
                relevant.append({
                    'reference': ref,
                    'relevance_score': overlap,
                    'matching_terms': list(sentence_words.intersection(ref_keywords))
                })
        
        # Sort by relevance score
        relevant.sort(key=lambda x: x['relevance_score'], reverse=True)
        return relevant

    async def generate_content_with_citations(
        self, 
        prompt: str, 
        context: Dict, 
        style: str,
        mission_id: str = None,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> ContentWithCitations:
        """
        Generate content with automatic citation integration.
        
        Args:
            prompt: The content generation prompt
            context: Context including available references and document info
            style: Citation style (APA, MLA, Chicago)
            mission_id: Optional mission ID for logging
            log_queue: Optional queue for UI updates
            update_callback: Optional callback for UI updates
            
        Returns:
            ContentWithCitations object with generated content and citations
        """
        self.mission_id = mission_id
        
        # Format available references for the prompt
        refs_context = ""
        if 'available_references' in context:
            refs_context = "\n\n**Available References:**\n"
            for ref in context['available_references']:
                refs_context += f"- [{ref.get('doc_id', 'unknown')}] {ref.get('title', 'Unknown Title')} ({ref.get('year', 'N/A')})\n"
        
        # Format document context
        doc_context = ""
        if 'document_structure' in context:
            doc_context = f"\n\n**Document Context:**\n{json.dumps(context['document_structure'], indent=2)}"
        
        generation_prompt = f"""Generate content for the following request, incorporating appropriate citations from the available references.

**Request:** {prompt}

**Citation Style:** {style}

**Guidelines:**
1. Generate clear, well-structured content that addresses the request
2. Incorporate relevant citations using [doc_id] format where appropriate
3. Ensure claims are properly supported with citations
4. Maintain consistency with the specified citation style
5. Consider the document context and structure when generating content

{refs_context}{doc_context}

**Generated Content:**"""

        try:
            # Call the LLM to generate content
            llm_response, model_call_details = await self._call_llm(
                user_prompt=generation_prompt,
                agent_mode="writing",
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            if llm_response and llm_response.choices:
                content = llm_response.choices[0].message.content.strip()
                
                # Extract citations from the generated content
                citations = re.findall(r'\[([^\]]+)\]', content)
                
                return ContentWithCitations(content=content, citations=citations)
            else:
                logger.error("Failed to generate content: No response from LLM")
                return ContentWithCitations(content="Error: Failed to generate content", citations=[])
                
        except Exception as e:
            logger.error(f"Error generating content with citations: {e}")
            return ContentWithCitations(content=f"Error: {str(e)}", citations=[])

    def analyze_document_structure(self, draft: Dict) -> StructureAnalysis:
        """
        Analyze document structure and identify potential issues.
        
        Args:
            draft: The document structure to analyze
            
        Returns:
            StructureAnalysis object with findings
        """
        sections = []
        total_word_count = 0
        issues = []
        
        def analyze_element(element, level=0):
            nonlocal total_word_count
            
            if element.get('type') == 'section':
                section_info = {
                    'id': element.get('id'),
                    'title': element.get('title'),
                    'level': level,
                    'paragraph_count': 0,
                    'word_count': 0
                }
                
                # Analyze children
                for child in element.get('children', []):
                    if child.get('type') == 'paragraph':
                        section_info['paragraph_count'] += 1
                        content = child.get('content', '')
                        word_count = len(content.split())
                        section_info['word_count'] += word_count
                        total_word_count += word_count
                        
                        # Check for issues in paragraphs
                        if word_count < 20:
                            issues.append(f"Very short paragraph in section '{section_info['title']}' (ID: {child.get('id')})")
                        elif word_count > 300:
                            issues.append(f"Very long paragraph in section '{section_info['title']}' (ID: {child.get('id')})")
                        
                        # Check for missing citations in research content
                        if not re.search(r'\[[^\]]+\]', content) and len(content.split()) > 50:
                            if any(indicator in content.lower() for indicator in ['research', 'study', 'findings', 'evidence']):
                                issues.append(f"Paragraph may need citations in section '{section_info['title']}' (ID: {child.get('id')})")
                    
                    elif child.get('type') == 'section':
                        analyze_element(child, level + 1)
                
                # Check section-level issues
                if section_info['paragraph_count'] == 0:
                    issues.append(f"Empty section: '{section_info['title']}' (ID: {section_info['id']})")
                elif section_info['word_count'] < 100 and level == 1:  # Main sections should have substantial content
                    issues.append(f"Very short main section: '{section_info['title']}' (ID: {section_info['id']})")
                
                sections.append(section_info)
        
        # Start analysis from document root
        if draft.get('type') == 'document':
            for child in draft.get('children', []):
                analyze_element(child)
        
        # Check overall document issues
        if total_word_count < 500:
            issues.append("Document is very short - consider adding more content")
        elif total_word_count > 10000:
            issues.append("Document is very long - consider breaking into smaller sections")
        
        if len(sections) < 3:
            issues.append("Document has few sections - consider adding more structure")
        
        return StructureAnalysis(sections=sections, word_count=total_word_count, issues=issues)

    def suggest_improvements(self, draft: Dict) -> List[Improvement]:
        """
        Suggest improvements for the document.
        
        Args:
            draft: The document structure to analyze
            
        Returns:
            List of Improvement objects
        """
        improvements = []
        analysis = self.analyze_document_structure(draft)
        
        # Convert analysis issues to improvements
        for issue in analysis.issues:
            if "very short paragraph" in issue.lower():
                improvements.append(Improvement(
                    type="content_expansion",
                    description=f"Expand short paragraph: {issue}",
                    priority="medium"
                ))
            elif "very long paragraph" in issue.lower():
                improvements.append(Improvement(
                    type="paragraph_split",
                    description=f"Consider splitting long paragraph: {issue}",
                    priority="medium"
                ))
            elif "may need citations" in issue.lower():
                improvements.append(Improvement(
                    type="citation_needed",
                    description=f"Add citations to support claims: {issue}",
                    priority="high"
                ))
            elif "empty section" in issue.lower():
                improvements.append(Improvement(
                    type="content_needed",
                    description=f"Add content to empty section: {issue}",
                    priority="high"
                ))
            else:
                improvements.append(Improvement(
                    type="general",
                    description=issue,
                    priority="medium"
                ))
        
        # Add structure-based improvements
        if len(analysis.sections) > 0:
            # Check for missing introduction/conclusion
            section_titles = [s['title'].lower() for s in analysis.sections]
            if not any('introduction' in title or 'intro' in title for title in section_titles):
                improvements.append(Improvement(
                    type="structure",
                    description="Consider adding an introduction section",
                    priority="medium"
                ))
            
            if not any('conclusion' in title or 'summary' in title for title in section_titles):
                improvements.append(Improvement(
                    type="structure",
                    description="Consider adding a conclusion section",
                    priority="medium"
                ))
        
        return improvements

    async def run(
        self,
        user_message: str,
        draft_id: str,
        context: Dict = None,
        mission_id: str = None,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None,
        **kwargs
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
        """
        Main execution method for collaborative writing assistance.
        
        Args:
            user_message: The user's message/request
            draft_id: ID of the draft being worked on
            context: Additional context including document structure, references, etc.
            mission_id: Optional mission ID for logging
            log_queue: Optional queue for UI updates
            update_callback: Optional callback for UI updates
            
        Returns:
            Tuple of (result_dict, model_details, scratchpad_update)
        """
        self.mission_id = mission_id
        context = context or {}
        
        logger.info(f"{self.agent_name}: Processing collaborative writing request for draft {draft_id}")
        
        try:
            # Parse structural commands from user message
            operations = self.parse_structural_commands(user_message)
            
            # Prepare response structure
            response = {
                'message': '',
                'operations_detected': len(operations),
                'operations': [op.__dict__ for op in operations],
                'suggestions': [],
                'content_generated': None
            }
            
            # If structural operations detected, explain what will be done
            if operations:
                op_descriptions = []
                for op in operations:
                    if op.operation_type == 'insert_section_after':
                        op_descriptions.append(f"Add section '{op.params.get('title')}'" + 
                                             (f" after {op.params.get('after_element')}" if op.params.get('after_element') else ""))
                    elif op.operation_type == 'insert_paragraph_after':
                        op_descriptions.append(f"Add paragraph about '{op.params.get('content_hint')}'" +
                                             (f" in {op.params.get('location')}" if op.params.get('location') else ""))
                    else:
                        op_descriptions.append(f"{op.operation_type}: {op.params}")
                
                response['message'] = f"I understand you want to make the following structural changes:\n" + \
                                    "\n".join(f"• {desc}" for desc in op_descriptions) + \
                                    "\n\nI can help you execute these changes using the document manipulation tools. Would you like me to proceed?"
            
            # If no structural operations, provide general writing assistance
            else:
                # Check if user is asking for content generation
                content_keywords = ['write', 'generate', 'create', 'add content', 'help me write']
                if any(keyword in user_message.lower() for keyword in content_keywords):
                    # Generate content with citations
                    content_result = await self.generate_content_with_citations(
                        prompt=user_message,
                        context=context,
                        style=context.get('citation_style', 'APA'),
                        mission_id=mission_id,
                        log_queue=log_queue,
                        update_callback=update_callback
                    )
                    
                    response['content_generated'] = {
                        'content': content_result.content,
                        'citations': content_result.citations
                    }
                    response['message'] = f"I've generated content for your request. The content includes {len(content_result.citations)} citations from available references."
                
                # Check if user is asking for analysis or suggestions
                elif any(keyword in user_message.lower() for keyword in ['analyze', 'review', 'suggestions', 'improve']):
                    if 'document_structure' in context:
                        improvements = self.suggest_improvements(context['document_structure'])
                        response['suggestions'] = [imp.__dict__ for imp in improvements]
                        response['message'] = f"I've analyzed your document and found {len(improvements)} suggestions for improvement. These include recommendations for content expansion, citation additions, and structural improvements."
                    else:
                        response['message'] = "I'd be happy to analyze your document, but I need access to the current document structure. Please ensure the document context is available."
                
                # General conversational response
                else:
                    response['message'] = """I'm here to help you with collaborative writing! I can assist with:

• **Structural Changes**: Add, move, or reorganize sections and paragraphs
• **Content Generation**: Create new content with automatic citations
• **Document Analysis**: Review structure and suggest improvements
• **Citation Management**: Add references and format citations
• **Style Improvements**: Enhance clarity and academic writing quality

What would you like to work on with your document?"""
            
            return response, None, f"Processed collaborative writing request: {len(operations)} operations detected"
            
        except Exception as e:
            logger.error(f"Error in CollaborativeWritingAgent.run: {e}")
            error_response = {
                'message': f"I encountered an error while processing your request: {str(e)}",
                'error': True
            }
            return error_response, None, f"Error in collaborative writing: {str(e)}"
