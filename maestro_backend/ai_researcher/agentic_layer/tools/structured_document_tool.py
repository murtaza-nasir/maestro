"""
Structured Document Tool for document manipulation operations.

This tool provides document structure manipulation capabilities for the CollaborativeWritingAgent,
interfacing with the Document Manipulation Engine services.
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StructuredDocumentInput(BaseModel):
    """Input schema for structured document operations."""
    operation: str = Field(..., description="The operation to perform: insert_paragraph_after, insert_section_after, split_paragraph, merge_paragraphs, move_section, update_content")
    draft_id: str = Field(..., description="ID of the draft to manipulate")
    target_element_id: Optional[str] = Field(None, description="ID of the target element for the operation")
    content: Optional[str] = Field(None, description="Content for insert/update operations")
    title: Optional[str] = Field(None, description="Title for section operations")
    level: Optional[int] = Field(1, description="Level for section operations (1-6)")
    references: Optional[List[str]] = Field(None, description="List of reference IDs to associate with content")
    split_position: Optional[int] = Field(None, description="Position to split paragraph at")
    paragraph_ids: Optional[List[str]] = Field(None, description="List of paragraph IDs for merge operations")
    target_parent_id: Optional[str] = Field(None, description="Target parent ID for move operations")
    position: Optional[int] = Field(None, description="Position within parent for move operations")


class StructuredDocumentTool:
    """
    Tool for manipulating structured document content through the Document Manipulation Engine.
    """
    
    def __init__(self):
        self.name = "structured_document"
        self.description = "Manipulates structured document content including sections and paragraphs. Supports operations like inserting, moving, splitting, merging, and updating document elements."
        self.parameters_schema = StructuredDocumentInput
        logger.info("StructuredDocumentTool initialized.")

    async def execute(
        self,
        operation: str,
        draft_id: str,
        target_element_id: Optional[str] = None,
        content: Optional[str] = None,
        title: Optional[str] = None,
        level: int = 1,
        references: Optional[List[str]] = None,
        split_position: Optional[int] = None,
        paragraph_ids: Optional[List[str]] = None,
        target_parent_id: Optional[str] = None,
        position: Optional[int] = None,
        mission_id: Optional[str] = None,
        agent_controller: Optional[Any] = None,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None,
        agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a structured document manipulation operation.
        
        Args:
            operation: The operation to perform
            draft_id: ID of the draft to manipulate
            target_element_id: ID of the target element
            content: Content for insert/update operations
            title: Title for section operations
            level: Level for section operations
            references: List of reference IDs
            split_position: Position to split paragraph at
            paragraph_ids: List of paragraph IDs for merge operations
            target_parent_id: Target parent ID for move operations
            position: Position within parent for move operations
            mission_id: Mission ID for logging
            agent_controller: Agent controller for accessing services
            log_queue: Queue for UI updates
            update_callback: Callback for UI updates
            agent_name: Name of the calling agent
            
        Returns:
            Dictionary with operation result
        """
        logger.info(f"StructuredDocumentTool: Executing {operation} on draft {draft_id}")
        
        try:
            # Import services here to avoid circular imports
            from services.document_structure_service import DocumentStructureService
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
                if operation == "insert_paragraph_after":
                    if not content:
                        return {"error": "Content is required for insert_paragraph_after operation"}
                    
                    result = await DocumentStructureService.insert_paragraph_after(
                        draft_id=draft_id,
                        target_element_id=target_element_id,
                        content=content,
                        references=references or [],
                        user_id=user_id
                    )
                    
                elif operation == "insert_section_after":
                    if not title:
                        return {"error": "Title is required for insert_section_after operation"}
                    
                    result = await DocumentStructureService.insert_section_after(
                        draft_id=draft_id,
                        target_element_id=target_element_id,
                        title=title,
                        level=level,
                        user_id=user_id
                    )
                    
                elif operation == "split_paragraph":
                    if not target_element_id or split_position is None:
                        return {"error": "target_element_id and split_position are required for split_paragraph operation"}
                    
                    result = await DocumentStructureService.split_paragraph(
                        draft_id=draft_id,
                        paragraph_id=target_element_id,
                        split_position=split_position,
                        user_id=user_id
                    )
                    
                elif operation == "merge_paragraphs":
                    if not paragraph_ids or len(paragraph_ids) < 2:
                        return {"error": "At least 2 paragraph_ids are required for merge_paragraphs operation"}
                    
                    result = await DocumentStructureService.merge_paragraphs(
                        draft_id=draft_id,
                        paragraph_ids=paragraph_ids,
                        user_id=user_id
                    )
                    
                elif operation == "move_section":
                    if not target_element_id or not target_parent_id:
                        return {"error": "target_element_id and target_parent_id are required for move_section operation"}
                    
                    result = await DocumentStructureService.move_section(
                        draft_id=draft_id,
                        section_id=target_element_id,
                        target_parent_id=target_parent_id,
                        position=position or 0,
                        user_id=user_id
                    )
                    
                elif operation == "update_content":
                    if not target_element_id or not content:
                        return {"error": "target_element_id and content are required for update_content operation"}
                    
                    result = await DocumentStructureService.update_content(
                        draft_id=draft_id,
                        element_id=target_element_id,
                        new_content=content,
                        user_id=user_id
                    )
                    
                else:
                    return {"error": f"Unknown operation: {operation}"}
                
                # Log successful operation
                if log_queue and update_callback and agent_controller:
                    try:
                        agent_controller.context_manager.log_execution_step(
                            mission_id=mission_id,
                            agent_name=agent_name or "StructuredDocumentTool",
                            action=f"Document Operation: {operation}",
                            input_summary=f"Draft: {draft_id}, Target: {target_element_id}",
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
                    "result": result,
                    "message": f"Successfully executed {operation} operation"
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error executing structured document operation {operation}: {e}")
            
            # Log failed operation
            if log_queue and update_callback and agent_controller:
                try:
                    agent_controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name=agent_name or "StructuredDocumentTool",
                        action=f"Document Operation: {operation}",
                        input_summary=f"Draft: {draft_id}, Target: {target_element_id}",
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
