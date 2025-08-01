"""
Reference Integration Tool for citation and reference management.

This tool provides reference management capabilities for the CollaborativeWritingAgent,
interfacing with the Reference Service for citation formatting and bibliography generation.
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReferenceIntegrationInput(BaseModel):
    """Input schema for reference integration operations."""
    operation: str = Field(..., description="The operation to perform: create_from_document, create_from_web, format_citation, generate_bibliography, add_to_element, extract_from_chunk")
    draft_id: str = Field(..., description="ID of the draft to work with")
    reference_id: Optional[str] = Field(None, description="ID of the reference for operations")
    element_id: Optional[str] = Field(None, description="ID of the document element to add reference to")
    citation_style: Optional[str] = Field("APA", description="Citation style: APA, MLA, or Chicago")
    document_chunk_id: Optional[str] = Field(None, description="ID of document chunk to create reference from")
    web_url: Optional[str] = Field(None, description="URL for web source reference")
    title: Optional[str] = Field(None, description="Title for web source reference")
    authors: Optional[List[str]] = Field(None, description="Authors for web source reference")
    year: Optional[str] = Field(None, description="Publication year for web source reference")
    reference_data: Optional[Dict[str, Any]] = Field(None, description="Reference data for formatting operations")
    chunk_data: Optional[Dict[str, Any]] = Field(None, description="Chunk data for extraction operations")


class ReferenceIntegrationTool:
    """
    Tool for managing references and citations through the Reference Service.
    """
    
    def __init__(self):
        self.name = "reference_integration"
        self.description = "Manages references and citations including creating references from documents/web sources, formatting citations, generating bibliographies, and adding references to document elements."
        self.parameters_schema = ReferenceIntegrationInput
        logger.info("ReferenceIntegrationTool initialized.")

    async def execute(
        self,
        operation: str,
        draft_id: str,
        reference_id: Optional[str] = None,
        element_id: Optional[str] = None,
        citation_style: str = "APA",
        document_chunk_id: Optional[str] = None,
        web_url: Optional[str] = None,
        title: Optional[str] = None,
        authors: Optional[List[str]] = None,
        year: Optional[str] = None,
        reference_data: Optional[Dict[str, Any]] = None,
        chunk_data: Optional[Dict[str, Any]] = None,
        mission_id: Optional[str] = None,
        agent_controller: Optional[Any] = None,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None,
        agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a reference integration operation.
        
        Args:
            operation: The operation to perform
            draft_id: ID of the draft to work with
            reference_id: ID of the reference for operations
            element_id: ID of the document element to add reference to
            citation_style: Citation style (APA, MLA, Chicago)
            document_chunk_id: ID of document chunk to create reference from
            web_url: URL for web source reference
            title: Title for web source reference
            authors: Authors for web source reference
            year: Publication year for web source reference
            reference_data: Reference data for formatting operations
            chunk_data: Chunk data for extraction operations
            mission_id: Mission ID for logging
            agent_controller: Agent controller for accessing services
            log_queue: Queue for UI updates
            update_callback: Callback for UI updates
            agent_name: Name of the calling agent
            
        Returns:
            Dictionary with operation result
        """
        logger.info(f"ReferenceIntegrationTool: Executing {operation} on draft {draft_id}")
        
        try:
            # Import services here to avoid circular imports
            from services.reference_service import ReferenceService
            from database.database import get_db
            from database.models import WritingSession
            from sqlalchemy.orm import Session
            
            # Get database session
            db_gen = get_db()
            db: Session = next(db_gen)
            
            try:
                # Get user ID from writing session
                session = db.query(WritingSession).join(WritingSession.chat).filter(
                    WritingSession.drafts.any(id=draft_id)
                ).first()
                
                if not session:
                    return {"error": f"Writing session not found for draft {draft_id}"}
                
                user_id = session.chat.user_id
                
                # Execute the requested operation
                if operation == "create_from_document":
                    if not document_chunk_id:
                        return {"error": "document_chunk_id is required for create_from_document operation"}
                    
                    result = await ReferenceService.create_reference_from_document_chunk(
                        draft_id=draft_id,
                        document_chunk_id=document_chunk_id,
                        citation_style=citation_style,
                        user_id=user_id
                    )
                    
                elif operation == "create_from_web":
                    if not web_url or not title:
                        return {"error": "web_url and title are required for create_from_web operation"}
                    
                    result = await ReferenceService.create_reference_from_web_source(
                        draft_id=draft_id,
                        web_url=web_url,
                        title=title,
                        authors=authors or [],
                        year=year,
                        citation_style=citation_style,
                        user_id=user_id
                    )
                    
                elif operation == "format_citation":
                    if not reference_data:
                        return {"error": "reference_data is required for format_citation operation"}
                    
                    result = await ReferenceService.format_citation(
                        reference_data=reference_data,
                        style=citation_style
                    )
                    
                elif operation == "generate_bibliography":
                    result = await ReferenceService.generate_bibliography(
                        draft_id=draft_id,
                        style=citation_style,
                        user_id=user_id
                    )
                    
                elif operation == "add_to_element":
                    if not reference_id or not element_id:
                        return {"error": "reference_id and element_id are required for add_to_element operation"}
                    
                    # Import document structure service for this operation
                    from services.document_structure_service import DocumentStructureService
                    
                    result = await DocumentStructureService.add_reference_to_element(
                        draft_id=draft_id,
                        element_id=element_id,
                        reference_id=reference_id,
                        user_id=user_id
                    )
                    
                elif operation == "extract_from_chunk":
                    if not chunk_data:
                        return {"error": "chunk_data is required for extract_from_chunk operation"}
                    
                    result = await ReferenceService.extract_reference_from_chunk(
                        chunk_data=chunk_data
                    )
                    
                else:
                    return {"error": f"Unknown operation: {operation}"}
                
                # Log successful operation
                if log_queue and update_callback and agent_controller:
                    try:
                        agent_controller.context_manager.log_execution_step(
                            mission_id=mission_id,
                            agent_name=agent_name or "ReferenceIntegrationTool",
                            action=f"Reference Operation: {operation}",
                            input_summary=f"Draft: {draft_id}, Style: {citation_style}",
                            output_summary=f"Operation completed successfully",
                            status="success",
                            log_queue=log_queue,
                            update_callback=update_callback
                        )
                    except Exception as log_error:
                        logger.warning(f"Failed to log operation: {log_error}")
                
                return {
                    "success": True,
                    "operation": operation,
                    "draft_id": draft_id,
                    "citation_style": citation_style,
                    "result": result,
                    "message": f"Successfully executed {operation} operation"
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error executing reference integration operation {operation}: {e}")
            
            # Log failed operation
            if log_queue and update_callback and agent_controller:
                try:
                    agent_controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name=agent_name or "ReferenceIntegrationTool",
                        action=f"Reference Operation: {operation}",
                        input_summary=f"Draft: {draft_id}, Style: {citation_style}",
                        output_summary=f"Operation failed: {str(e)}",
                        status="failure",
                        error_message=str(e),
                        log_queue=log_queue,
                        update_callback=update_callback
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to log operation error: {log_error}")
            
            return {
                "error": f"Failed to execute {operation} operation: {str(e)}",
                "operation": operation,
                "draft_id": draft_id
            }
