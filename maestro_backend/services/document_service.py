"""
Document Service - Wrapper for V2 Implementation

This module provides backward compatibility by exposing the V2 implementation
with the original module name. The system has been migrated from the dual-database
architecture (SQLite + ChromaDB) to a unified PostgreSQL + pgvector architecture.

The V2 implementation provides:
- Unified PostgreSQL database for all metadata
- pgvector for semantic search
- Saga pattern for transactional consistency
- Event-driven processing with proper rollback
"""

from services.document_service_v2 import UnifiedDocumentService
from database.database import get_db
from typing import List, Dict
import re
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Export the V2 service with a compatible name
DocumentService = UnifiedDocumentService

# Create a singleton instance for backward compatibility
# Initialize with a database session on first use
_document_service_instance = None

def get_document_service(db=None):
    """Get or create the document service instance."""
    global _document_service_instance
    if _document_service_instance is None:
        if db is None:
            # Get a new database session if not provided
            db = next(get_db())
        _document_service_instance = DocumentService(db)
    return _document_service_instance

# Create a singleton that will be initialized lazily
class LazyDocumentService:
    """Lazy initialization wrapper for document service with document code support."""
    
    def extract_document_codes_from_text(self, text: str) -> List[str]:
        """
        Extract document codes (UUIDs) from text.
        Handles:
        - Full UUIDs (36 chars): xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        - 8-char prefixes in paths: /markdown/xxxxxxxx.md
        - Chunk IDs: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx_0
        """
        codes = set()
        
        # Pattern for full UUIDs
        uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
        matches = re.findall(uuid_pattern, text, re.IGNORECASE)
        codes.update(matches)
        
        # Pattern for 8-char hex codes (legacy format)
        # Look for them in markdown paths
        markdown_pattern = r'/(?:markdown|processed/markdown)/([a-f0-9]{8})\.md'
        matches = re.findall(markdown_pattern, text, re.IGNORECASE)
        codes.update(matches)
        
        # Pattern for standalone 8-char hex codes
        # Be careful to match only valid document IDs
        standalone_pattern = r'\b([a-f0-9]{8})\b(?!-[a-f0-9])'  # Not followed by more UUID parts
        matches = re.findall(standalone_pattern, text, re.IGNORECASE)
        # Filter to avoid false positives (only add if it looks like a doc reference)
        for match in matches:
            # Check if this 8-char code appears in a document-like context
            if f'{match}.md' in text or f'/{match}' in text or f'{match}_' in text:
                codes.add(match)
        
        return list(codes)
    
    async def get_document_filename_mapping(self, document_codes: List[str]) -> Dict[str, str]:
        """
        Map document codes (UUIDs or 8-char prefixes) to filenames.
        Queries PostgreSQL documents table for the mappings.
        """
        if not document_codes:
            return {}
        
        try:
            db = next(get_db())
            
            # Prepare the query to handle both full UUIDs and 8-char prefixes
            # Separate full UUIDs from 8-char codes
            full_uuids = [code for code in document_codes if len(code) == 36 and '-' in code]
            short_codes = [code for code in document_codes if len(code) == 8]
            
            code_to_filename = {}
            
            # Query for full UUIDs
            if full_uuids:
                query = text("""
                    SELECT id::text as doc_id, filename
                    FROM documents
                    WHERE id::text = ANY(:uuids)
                """)
                result = db.execute(query, {'uuids': full_uuids})
                for row in result:
                    code_to_filename[row.doc_id] = row.filename
            
            # Query for 8-char prefixes
            if short_codes:
                # PostgreSQL query to match by UUID prefix
                query = text("""
                    SELECT id::text as doc_id, filename, LEFT(id::text, 8) as short_id
                    FROM documents
                    WHERE LEFT(id::text, 8) = ANY(:codes)
                """)
                result = db.execute(query, {'codes': short_codes})
                for row in result:
                    # Map both the short code and full UUID to filename
                    code_to_filename[row.short_id] = row.filename
                    code_to_filename[row.doc_id] = row.filename
            
            # For any codes not found, use the code itself as fallback
            for code in document_codes:
                if code not in code_to_filename:
                    code_to_filename[code] = code
            
            logger.debug(f"Mapped {len(code_to_filename)} document codes to filenames")
            return code_to_filename
            
        except Exception as e:
            logger.error(f"Error mapping document codes to filenames: {e}")
            # Return codes as-is on error
            return {code: code for code in document_codes}
        finally:
            if 'db' in locals():
                db.close()
    
    async def replace_document_codes_in_text(self, text: str) -> str:
        """
        Replace document codes with human-readable filenames in text.
        Handles various formats: paths, standalone UUIDs, chunk IDs.
        """
        if not text:
            return text
        
        # Extract all document codes from the text
        document_codes = self.extract_document_codes_from_text(text)
        
        if not document_codes:
            return text
        
        # Get filename mappings
        code_to_filename = await self.get_document_filename_mapping(document_codes)
        
        # Replace codes in the text
        result_text = text
        
        for code, filename in code_to_filename.items():
            if code != filename:  # Only replace if we found a different filename
                # Remove .pdf extension if present for cleaner display
                display_name = filename
                if display_name.endswith('.pdf'):
                    display_name = display_name[:-4]
                
                # Replace in various contexts
                # 1. Full UUID references
                if len(code) == 36:  # Full UUID
                    result_text = re.sub(
                        r'\b' + re.escape(code) + r'\b',
                        display_name,
                        result_text
                    )
                    # Also replace chunk IDs (UUID_number)
                    result_text = re.sub(
                        re.escape(code) + r'_\d+',
                        display_name,
                        result_text
                    )
                
                # 2. 8-char codes in paths
                if len(code) == 8:
                    # Replace in markdown paths
                    result_text = result_text.replace(
                        f'/markdown/{code}.md',
                        display_name
                    )
                    result_text = result_text.replace(
                        f'/processed/markdown/{code}.md',
                        display_name
                    )
                    # Replace standalone 8-char codes
                    result_text = re.sub(
                        r'\b' + re.escape(code) + r'\b(?!-[a-f0-9])',
                        display_name,
                        result_text
                    )
        
        return result_text
    
    def __getattr__(self, name):
        # Delegate to UnifiedDocumentService for methods we don't override
        service = get_document_service()
        return getattr(service, name)

# Export a lazy singleton for backward compatibility
document_service = LazyDocumentService()

# For modules that import document_service directly
__all__ = ['DocumentService', 'get_document_service', 'document_service']