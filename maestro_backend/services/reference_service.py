"""
Reference Management Service for handling citations and references.

This service manages the extraction, formatting, and validation of references
from RAG documents and web sources. It provides intelligent citation formatting
and reference management capabilities.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import re
from sqlalchemy.orm import Session
from database import models
from fastapi import HTTPException, status


class ReferenceService:
    """Service for managing references and citations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def extract_reference_from_chunk(self, chunk_data: Dict) -> Dict:
        """Extract citation data from RAG document chunk."""
        
        # Extract metadata from chunk
        metadata = chunk_data.get("metadata", {})
        
        # Build reference data structure
        reference_data = {
            "type": "document",
            "title": metadata.get("title", "Unknown Title"),
            "authors": self._parse_authors(metadata.get("authors", "")),
            "year": self._extract_year(metadata.get("year") or metadata.get("date")),
            "journal": metadata.get("journal", ""),
            "volume": metadata.get("volume", ""),
            "issue": metadata.get("issue", ""),
            "pages": metadata.get("pages", ""),
            "doi": metadata.get("doi", ""),
            "url": metadata.get("url", ""),
            "publisher": metadata.get("publisher", ""),
            "source_document_id": chunk_data.get("document_id"),
            "source_chunk_id": chunk_data.get("chunk_id"),
            "page_number": metadata.get("page_number", "")
        }
        
        return reference_data
    
    def _parse_authors(self, authors_str: str) -> List[str]:
        """Parse author string into list of individual authors."""
        if not authors_str:
            return []
        
        # Handle common author separators
        separators = [";", ",", " and ", " & "]
        authors = [authors_str]
        
        for sep in separators:
            new_authors = []
            for author in authors:
                new_authors.extend([a.strip() for a in author.split(sep)])
            authors = new_authors
        
        # Clean up and filter empty strings
        return [author.strip() for author in authors if author.strip()]
    
    def _extract_year(self, date_str: Any) -> Optional[int]:
        """Extract year from date string or return None."""
        if not date_str:
            return None
        
        # Convert to string if it's not already
        date_str = str(date_str)
        
        # Look for 4-digit year
        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if year_match:
            return int(year_match.group())
        
        return None
    
    async def format_citation(self, reference_data: Dict, style: str = "APA") -> str:
        """Format citation according to style guide."""
        
        style = style.upper()
        
        if style == "APA":
            return self._format_apa_citation(reference_data)
        elif style == "MLA":
            return self._format_mla_citation(reference_data)
        elif style == "CHICAGO":
            return self._format_chicago_citation(reference_data)
        else:
            # Default to APA
            return self._format_apa_citation(reference_data)
    
    def _format_apa_citation(self, ref: Dict) -> str:
        """Format citation in APA style."""
        
        # Handle authors
        authors = ref.get("authors", [])
        if not authors:
            author_str = "Unknown Author"
        elif len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} & {authors[1]}"
        else:
            # Multiple authors: First, Second, & Last
            author_str = ", ".join(authors[:-1]) + f", & {authors[-1]}"
        
        # Handle year
        year = ref.get("year")
        year_str = f"({year})" if year else "(n.d.)"
        
        # Handle title
        title = ref.get("title", "Untitled")
        
        # Handle journal/publication info
        journal = ref.get("journal", "")
        volume = ref.get("volume", "")
        issue = ref.get("issue", "")
        pages = ref.get("pages", "")
        
        # Build citation
        citation_parts = [author_str, year_str, title]
        
        if journal:
            journal_part = journal
            if volume:
                journal_part += f", {volume}"
                if issue:
                    journal_part += f"({issue})"
            if pages:
                journal_part += f", {pages}"
            citation_parts.append(journal_part)
        
        # Add DOI or URL if available
        doi = ref.get("doi", "")
        url = ref.get("url", "")
        if doi:
            citation_parts.append(f"https://doi.org/{doi}")
        elif url:
            citation_parts.append(url)
        
        return ". ".join(citation_parts) + "."
    
    def _format_mla_citation(self, ref: Dict) -> str:
        """Format citation in MLA style."""
        
        # Handle authors (Last, First format for MLA)
        authors = ref.get("authors", [])
        if not authors:
            author_str = "Unknown Author"
        else:
            # For MLA, reverse first author name
            first_author = authors[0]
            if "," in first_author:
                author_str = first_author
            else:
                # Try to reverse "First Last" to "Last, First"
                parts = first_author.split()
                if len(parts) >= 2:
                    author_str = f"{parts[-1]}, {' '.join(parts[:-1])}"
                else:
                    author_str = first_author
            
            # Add additional authors
            if len(authors) > 1:
                author_str += ", et al."
        
        # Handle title (italicized for journals)
        title = f'"{ref.get("title", "Untitled")}"'
        
        # Handle journal
        journal = ref.get("journal", "")
        if journal:
            journal = f"{journal},"
        
        # Handle volume, issue, year, pages
        volume = ref.get("volume", "")
        issue = ref.get("issue", "")
        year = ref.get("year", "")
        pages = ref.get("pages", "")
        
        # Build citation
        citation_parts = [author_str, title]
        if journal:
            citation_parts.append(journal)
        
        vol_info = []
        if volume:
            vol_info.append(f"vol. {volume}")
        if issue:
            vol_info.append(f"no. {issue}")
        if year:
            vol_info.append(str(year))
        if pages:
            vol_info.append(f"pp. {pages}")
        
        if vol_info:
            citation_parts.append(", ".join(vol_info))
        
        return " ".join(citation_parts) + "."
    
    def _format_chicago_citation(self, ref: Dict) -> str:
        """Format citation in Chicago style."""
        
        # Handle authors
        authors = ref.get("authors", [])
        if not authors:
            author_str = "Unknown Author"
        else:
            author_str = ", ".join(authors)
        
        # Handle title
        title = f'"{ref.get("title", "Untitled")}"'
        
        # Handle journal
        journal = ref.get("journal", "")
        
        # Handle volume, issue, year, pages
        volume = ref.get("volume", "")
        issue = ref.get("issue", "")
        year = ref.get("year", "")
        pages = ref.get("pages", "")
        
        # Build citation
        citation_parts = [author_str, title]
        
        if journal:
            journal_part = journal
            if volume:
                journal_part += f" {volume}"
                if issue:
                    journal_part += f", no. {issue}"
            if year:
                journal_part += f" ({year})"
            if pages:
                journal_part += f": {pages}"
            citation_parts.append(journal_part)
        
        return ". ".join(citation_parts) + "."
    
    async def generate_in_text_citation(self, reference_data: Dict, style: str = "APA") -> str:
        """Generate in-text citation."""
        
        style = style.upper()
        
        if style == "APA":
            return self._generate_apa_in_text(reference_data)
        elif style == "MLA":
            return self._generate_mla_in_text(reference_data)
        elif style == "CHICAGO":
            return self._generate_chicago_in_text(reference_data)
        else:
            return self._generate_apa_in_text(reference_data)
    
    def _generate_apa_in_text(self, ref: Dict) -> str:
        """Generate APA in-text citation."""
        
        authors = ref.get("authors", [])
        year = ref.get("year", "n.d.")
        
        if not authors:
            author_part = "Unknown Author"
        elif len(authors) == 1:
            # Extract last name
            author_part = authors[0].split()[-1] if authors[0] else "Unknown"
        elif len(authors) == 2:
            last_names = [author.split()[-1] for author in authors]
            author_part = f"{last_names[0]} & {last_names[1]}"
        else:
            # Multiple authors
            first_last_name = authors[0].split()[-1] if authors[0] else "Unknown"
            author_part = f"{first_last_name} et al."
        
        return f"({author_part}, {year})"
    
    def _generate_mla_in_text(self, ref: Dict) -> str:
        """Generate MLA in-text citation."""
        
        authors = ref.get("authors", [])
        pages = ref.get("pages", "")
        
        if not authors:
            author_part = "Unknown Author"
        else:
            # Use last name of first author
            author_part = authors[0].split()[-1] if authors[0] else "Unknown"
        
        if pages:
            return f"({author_part} {pages})"
        else:
            return f"({author_part})"
    
    def _generate_chicago_in_text(self, ref: Dict) -> str:
        """Generate Chicago in-text citation (author-date style)."""
        
        authors = ref.get("authors", [])
        year = ref.get("year", "n.d.")
        pages = ref.get("pages", "")
        
        if not authors:
            author_part = "Unknown Author"
        else:
            author_part = authors[0].split()[-1] if authors[0] else "Unknown"
        
        citation = f"({author_part} {year}"
        if pages:
            citation += f", {pages}"
        citation += ")"
        
        return citation
    
    async def auto_detect_citation_style(self, existing_references: List[Dict]) -> str:
        """Auto-detect citation style from existing references."""
        
        if not existing_references:
            return "APA"  # Default
        
        # Look for style indicators in existing citations
        apa_indicators = 0
        mla_indicators = 0
        chicago_indicators = 0
        
        for ref in existing_references:
            citation_text = ref.get("citation_text", "")
            
            # APA indicators: (Year), & between authors
            if re.search(r'\(\d{4}\)', citation_text) or ' & ' in citation_text:
                apa_indicators += 1
            
            # MLA indicators: "Title", vol., no., pp.
            if '"' in citation_text and ('vol.' in citation_text or 'pp.' in citation_text):
                mla_indicators += 1
            
            # Chicago indicators: similar to APA but different patterns
            if re.search(r'\(\d{4}\)', citation_text) and 'no.' in citation_text:
                chicago_indicators += 1
        
        # Return most likely style
        if mla_indicators > apa_indicators and mla_indicators > chicago_indicators:
            return "MLA"
        elif chicago_indicators > apa_indicators:
            return "CHICAGO"
        else:
            return "APA"
    
    async def validate_reference_completeness(self, reference_data: Dict) -> List[str]:
        """Check for missing required fields."""
        
        missing_fields = []
        
        # Required fields for most citation styles
        required_fields = ["title", "authors", "year"]
        
        for field in required_fields:
            if not reference_data.get(field):
                missing_fields.append(field)
        
        # Check for publication info (journal OR publisher)
        if not reference_data.get("journal") and not reference_data.get("publisher"):
            missing_fields.append("journal_or_publisher")
        
        return missing_fields
    
    async def create_reference_from_document_chunk(
        self, 
        draft_id: str, 
        document_chunk_id: str, 
        citation_style: str = "APA",
        user_id: int = None
    ) -> models.Reference:
        """Create a reference from a document chunk."""
        
        # Validate draft access
        draft = self.db.query(models.Draft).join(
            models.WritingSession, models.Draft.writing_session_id == models.WritingSession.id
        ).join(
            models.Chat, models.WritingSession.chat_id == models.Chat.id
        ).filter(
            models.Draft.id == draft_id,
            models.Chat.user_id == user_id
        ).first()
        
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found or access denied"
            )
        
        # TODO: Extract chunk data from vector store
        # For now, create a placeholder reference
        chunk_data = {
            "document_id": "doc_placeholder",
            "chunk_id": document_chunk_id,
            "metadata": {
                "title": "Document Title",
                "authors": "Author Name",
                "year": "2024"
            }
        }
        
        # Extract reference data
        reference_data = await self.extract_reference_from_chunk(chunk_data)
        
        # Format citation
        citation_text = await self.format_citation(reference_data, citation_style)
        
        # Create reference record
        reference = models.Reference(
            id=str(uuid.uuid4()),
            draft_id=draft_id,
            document_id=reference_data.get("source_document_id"),
            citation_text=citation_text,
            context="",  # Will be filled when reference is used
            reference_type="document",
            created_at=datetime.utcnow()
        )
        
        self.db.add(reference)
        self.db.commit()
        self.db.refresh(reference)
        
        return reference
    
    async def create_reference_from_web_source(
        self, 
        draft_id: str, 
        web_url: str, 
        title: str, 
        authors: str = "", 
        year: str = "",
        citation_style: str = "APA",
        user_id: int = None
    ) -> models.Reference:
        """Create a reference from a web source."""
        
        # Validate draft access
        draft = self.db.query(models.Draft).join(
            models.WritingSession, models.Draft.writing_session_id == models.WritingSession.id
        ).join(
            models.Chat, models.WritingSession.chat_id == models.Chat.id
        ).filter(
            models.Draft.id == draft_id,
            models.Chat.user_id == user_id
        ).first()
        
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found or access denied"
            )
        
        # Build reference data
        reference_data = {
            "type": "web",
            "title": title,
            "authors": self._parse_authors(authors),
            "year": self._extract_year(year),
            "url": web_url
        }
        
        # Format citation
        citation_text = await self.format_citation(reference_data, citation_style)
        
        # Create reference record
        reference = models.Reference(
            id=str(uuid.uuid4()),
            draft_id=draft_id,
            web_url=web_url,
            citation_text=citation_text,
            context="",
            reference_type="web",
            created_at=datetime.utcnow()
        )
        
        self.db.add(reference)
        self.db.commit()
        self.db.refresh(reference)
        
        return reference
    
    async def get_references_for_draft(
        self, 
        draft_id: str,
        user_id: int = None
    ) -> List[models.Reference]:
        """Get all references for a draft."""
        
        # Validate draft access
        draft = self.db.query(models.Draft).join(
            models.WritingSession, models.Draft.writing_session_id == models.WritingSession.id
        ).join(
            models.Chat, models.WritingSession.chat_id == models.Chat.id
        ).filter(
            models.Draft.id == draft_id,
            models.Chat.user_id == user_id
        ).first()
        
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found or access denied"
            )
        
        # Get references
        references = self.db.query(models.Reference).filter(
            models.Reference.draft_id == draft_id
        ).order_by(models.Reference.created_at).all()
        
        return references
    
    async def update_reference(
        self, 
        reference_id: str, 
        citation_text: str = None,
        context: str = None,
        user_id: int = None
    ) -> models.Reference:
        """Update an existing reference."""
        
        # Get reference and validate access
        reference = self.db.query(models.Reference).join(
            models.Draft, models.Reference.draft_id == models.Draft.id
        ).join(
            models.WritingSession, models.Draft.writing_session_id == models.WritingSession.id
        ).join(
            models.Chat, models.WritingSession.chat_id == models.Chat.id
        ).filter(
            models.Reference.id == reference_id,
            models.Chat.user_id == user_id
        ).first()
        
        if not reference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reference not found or access denied"
            )
        
        # Update fields
        if citation_text is not None:
            reference.citation_text = citation_text
        if context is not None:
            reference.context = context
        
        self.db.commit()
        self.db.refresh(reference)
        
        return reference
