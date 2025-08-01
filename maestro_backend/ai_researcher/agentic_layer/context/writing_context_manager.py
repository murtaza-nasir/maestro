"""
Writing Context Manager for Collaborative Writing Agent

Handles comprehensive context assembly for writing operations including:
- Document structure and outline
- References and citations
- Conversation history
- Document group content
- Search results integration
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json

from database import models
from services.document_structure_service import DocumentStructureService
from services.reference_service import ReferenceService


class WritingContextManager:
    """Manages context assembly for collaborative writing operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.doc_service = DocumentStructureService(db)
        self.ref_service = ReferenceService(db)

    def get_document_structure_service(self) -> DocumentStructureService:
        """Returns the document structure service instance."""
        return self.doc_service
    
    async def assemble_context(
        self,
        draft_id: str,
        draft: Any,
        user_id: int,
        request_type: str = "general",
        settings: Optional[Dict[str, Any]] = None,
        context_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Assemble comprehensive context for writing operations.
        
        Args:
            draft_id: ID of the current draft
            draft: The verified draft object
            user_id: ID of the user
            request_type: Type of request ('research_heavy', 'writing_focused', 'balanced')
            settings: Writing session settings
            context_override: Override default context inclusion
            
        Returns:
            Comprehensive context dictionary
        """
        
        # Get default settings
        default_settings = self._get_default_context_settings()
        if settings and settings.get('context_settings'):
            default_settings.update(settings['context_settings'])
        
        # Apply context overrides
        if context_override:
            default_settings.update(context_override)
        
        if not draft:
            raise ValueError(f"Draft {draft_id} not found or access denied")
        
        context = {
            'draft_id': draft_id,
            'draft_title': draft.title,
            'draft_version': draft.version,
            'timestamp': datetime.utcnow().isoformat(),
            'request_type': request_type,
            'settings_applied': default_settings
        }
        
        # Always include document outline
        if default_settings.get('always_include_outline', True):
            context['document_outline'] = await self._get_document_outline(draft)
        
        # Include full document based on threshold or request type
        include_full_doc = self._should_include_full_document(
            draft, request_type, default_settings
        )
        if include_full_doc:
            context['full_document'] = draft.content
        
        # Include references
        if default_settings.get('include_references', True):
            context['references'] = await self._get_references_context(draft_id, user_id)
        
        # Include conversation history
        if default_settings.get('include_conversation_history', True):
            context['conversation_history'] = await self._get_conversation_history(
                draft.writing_session_id, 
                limit=default_settings.get('conversation_history_limit', 10)
            )
        
        # Include document group context if available
        writing_session = draft.writing_session
        if writing_session.document_group_id and default_settings.get('include_document_group', True):
            context['document_group'] = await self._get_document_group_context(
                writing_session.document_group_id, user_id
            )
        
        # Include citation style and formatting preferences
        context['citation_style'] = draft.content.get('metadata', {}).get('reference_style', 'APA')
        
        # Include writing session settings
        if writing_session.settings:
            context['session_settings'] = writing_session.settings
        
        return context
    
    def _get_default_context_settings(self) -> Dict[str, Any]:
        """Get default context inclusion settings."""
        return {
            'always_include_outline': True,
            'include_full_document_threshold': 5000,  # words
            'include_references': True,
            'include_conversation_history': True,
            'include_document_group': True,
            'conversation_history_limit': 10,
            'max_context_window': 32000  # tokens
        }
    
    async def _get_document_outline(self, draft: models.Draft) -> Dict[str, Any]:
        """Extract document outline from draft content."""
        content = draft.content
        
        def extract_outline(node, level=0):
            outline = []
            if isinstance(node, dict):
                if node.get('type') == 'section':
                    outline.append({
                        'id': node.get('id'),
                        'title': node.get('title', 'Untitled Section'),
                        'level': level,
                        'word_count': self._count_words_in_node(node)
                    })
                    level += 1
                
                # Process children
                children = node.get('children', [])
                for child in children:
                    outline.extend(extract_outline(child, level))
            
            return outline
        
        return {
            'title': content.get('metadata', {}).get('title', draft.title),
            'sections': extract_outline(content),
            'total_word_count': self._count_words_in_node(content),
            'last_modified': content.get('metadata', {}).get('last_modified')
        }
    
    def _count_words_in_node(self, node) -> int:
        """Count words in a document node."""
        if isinstance(node, dict):
            word_count = 0
            
            # Count words in text content
            if node.get('type') == 'paragraph' and node.get('content'):
                word_count += len(node['content'].split())
            
            # Recursively count in children
            children = node.get('children', [])
            for child in children:
                word_count += self._count_words_in_node(child)
            
            return word_count
        
        return 0
    
    def _should_include_full_document(
        self, 
        draft: models.Draft, 
        request_type: str, 
        settings: Dict[str, Any]
    ) -> bool:
        """Determine if full document should be included in context."""
        
        # Always include for writing-focused requests
        if request_type == 'writing_focused':
            return True
        
        # Check word count threshold
        word_count = self._count_words_in_node(draft.content)
        threshold = settings.get('include_full_document_threshold', 5000)
        
        return word_count <= threshold
    
    async def _get_references_context(self, draft_id: str, user_id: int) -> List[Dict[str, Any]]:
        """Get references context for the draft."""
        references = await self.ref_service.get_references_for_draft(draft_id, user_id)
        
        return [
            {
                'id': ref.id,
                'citation_text': ref.citation_text,
                'reference_type': ref.reference_type,
                'context': ref.context,
                'created_at': ref.created_at.isoformat()
            }
            for ref in references
        ]
    
    async def _get_conversation_history(
        self, 
        writing_session_id: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent conversation history for the writing session."""
        
        # Get the chat associated with this writing session
        writing_session = self.db.query(models.WritingSession).filter(
            models.WritingSession.id == writing_session_id
        ).first()
        
        if not writing_session:
            return []
        
        # Get recent messages from the chat
        messages = self.db.query(models.Message).filter(
            models.Message.chat_id == writing_session.chat_id
        ).order_by(models.Message.created_at.desc()).limit(limit).all()
        
        return [
            {
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.created_at.isoformat()
            }
            for msg in reversed(messages)  # Reverse to get chronological order
        ]
    
    async def _get_document_group_context(
        self, 
        document_group_id: str, 
        user_id: int
    ) -> Dict[str, Any]:
        """Get document group context for RAG operations."""
        
        # Get document group
        doc_group = self.db.query(models.DocumentGroup).filter(
            models.DocumentGroup.id == document_group_id,
            models.DocumentGroup.user_id == user_id
        ).first()
        
        if not doc_group:
            return {}
        
        # Get document summaries
        documents = self.db.query(models.Document).filter(
            models.Document.id.in_([doc.id for doc in doc_group.documents])
        ).all()
        
        return {
            'group_id': doc_group.id,
            'group_name': doc_group.name,
            'group_description': doc_group.description,
            'document_count': len(documents),
            'documents': [
                {
                    'id': doc.id,
                    'title': doc.metadata_.get('title') if doc.metadata_ else doc.original_filename,
                    'authors': doc.metadata_.get('authors') if doc.metadata_ else [],
                    'filename': doc.original_filename
                }
                for doc in documents
                if doc.processing_status == 'completed'
            ]
        }
    
    async def add_search_results_to_context(
        self, 
        context: Dict[str, Any], 
        search_results: List[Dict[str, Any]],
        search_query: str,
        revision_step: int = 1
    ) -> Dict[str, Any]:
        """Add search results to existing context."""
        
        if 'search_results' not in context:
            context['search_results'] = []
        
        context['search_results'].append({
            'query': search_query,
            'revision_step': revision_step,
            'timestamp': datetime.utcnow().isoformat(),
            'results': search_results,
            'result_count': len(search_results)
        })
        
        return context
    
    def estimate_context_tokens(self, context: Dict[str, Any]) -> int:
        """Estimate token count for context (rough approximation)."""
        
        # Convert context to string and estimate tokens
        context_str = json.dumps(context, default=str)
        
        # Rough estimation: 1 token ≈ 4 characters
        estimated_tokens = len(context_str) // 4
        
        return estimated_tokens
    
    def trim_context_to_limit(
        self, 
        context: Dict[str, Any], 
        max_tokens: int = 32000
    ) -> Dict[str, Any]:
        """Trim context to fit within token limit."""
        
        current_tokens = self.estimate_context_tokens(context)
        
        if current_tokens <= max_tokens:
            return context
        
        # Priority order for trimming (keep most important)
        trim_order = [
            'search_results',  # Keep only most recent
            'conversation_history',  # Reduce limit
            'full_document',  # Remove if present
            'document_group'  # Reduce document details
        ]
        
        for field in trim_order:
            if current_tokens <= max_tokens:
                break
                
            if field in context:
                if field == 'search_results' and len(context[field]) > 1:
                    # Keep only the most recent search result
                    context[field] = context[field][-1:]
                elif field == 'conversation_history' and len(context[field]) > 5:
                    # Reduce conversation history
                    context[field] = context[field][-5:]
                elif field == 'full_document':
                    # Remove full document, keep only outline
                    del context[field]
                elif field == 'document_group':
                    # Simplify document group info
                    if 'documents' in context[field]:
                        context[field]['documents'] = context[field]['documents'][:5]
                
                current_tokens = self.estimate_context_tokens(context)
        
        return context
