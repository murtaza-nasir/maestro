import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from database import crud, models
from api import schemas
from auth.dependencies import get_current_user_from_cookie
from database.database import get_db
from services.document_service import document_service
from api.websockets import send_document_update
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# New endpoint to get all documents from the existing vector store
@router.get("/all-documents/", response_model=schemas.PaginatedDocumentResponse)
async def get_all_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in title, authors, filename"),
    author: Optional[str] = Query(None, description="Filter by author"),
    year: Optional[int] = Query(None, description="Filter by publication year"),
    journal: Optional[str] = Query(None, description="Filter by journal/source"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    sort_by: Optional[str] = Query("created_at", description="Field to sort by"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc")
):
    """
    Get all documents from the AI researcher database with filtering and pagination (optimized).
    """
    # Use the optimized paginated method that queries the AI researcher database directly
    result = await document_service.get_paginated_documents(
        user_id=current_user.id,
        page=page,
        limit=limit,
        search=search,
        author=author,
        year=year,
        journal=journal,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Convert documents to schema format
    validated_documents = []
    validation_errors = 0
    
    for i, doc in enumerate(result['documents']):
        try:
            validated_doc = schemas.Document(**doc)
            validated_documents.append(validated_doc)
        except Exception as e:
            validation_errors += 1
            if validation_errors <= 5:  # Only print first 5 errors
                logger.debug(f"API DEBUG: Validation error for document {i}: {e}")
                logger.debug(f"API DEBUG: Document data: {doc}")
    
    logger.debug(f"API DEBUG: {len(validated_documents)} documents passed validation, {validation_errors} failed")
    
    # Create pagination info
    pagination_info = schemas.PaginationInfo(
        total_count=result['pagination']['total_count'],
        page=result['pagination']['page'],
        limit=result['pagination']['limit'],
        total_pages=result['pagination']['total_pages'],
        has_next=result['pagination']['has_next'],
        has_previous=result['pagination']['has_previous']
    )
    
    logger.debug(f"API DEBUG: Filtered to {result['pagination']['total_count']} documents, returning page {page} with {len(validated_documents)} items")
    
    return schemas.PaginatedDocumentResponse(
        documents=validated_documents,
        pagination=pagination_info,
        filters_applied=result['filters_applied']
    )

# New endpoint to search documents
@router.get("/search/")
async def search_documents(
    query: str = Query(..., description="Search query"),
    n_results: int = Query(10, description="Number of results to return"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Search documents using the existing vector store.
    """
    results = await document_service.search_documents(query, current_user.id, n_results)
    return {"results": results}

# New endpoint to add existing document to group
@router.post("/document-groups/{group_id}/add-document/{doc_id}")
async def add_existing_document_to_group(
    group_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Add an existing document from the vector store to a group.
    """
    success = await document_service.add_document_to_group(group_id, doc_id, current_user.id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be added to group")
    return {"message": "Document added to group successfully"}

# New endpoint to upload and process documents
@router.post("/document-groups/{group_id}/upload/")
async def upload_document_to_group(
    group_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Upload a new document and add it to a group.
    """
    # Check for supported file formats
    filename_lower = file.filename.lower()
    supported_extensions = ['.pdf', '.docx', '.doc', '.md', '.markdown']
    
    if not any(filename_lower.endswith(ext) for ext in supported_extensions):
        raise HTTPException(
            status_code=400, 
            detail="Only PDF, Word (docx, doc), and Markdown (md, markdown) files are supported"
        )
    
    file_content = await file.read()
    result = await document_service.upload_document(
        file_content, file.filename, group_id, current_user.id, db
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to upload and process document")
    
    return result

# New endpoint to get documents in a group (integrates with existing vector store)
@router.get("/document-groups/{group_id}/documents/", response_model=schemas.PaginatedDocumentResponse)
async def get_documents_in_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in title, authors, filename"),
    author: Optional[str] = Query(None, description="Filter by author"),
    year: Optional[int] = Query(None, description="Filter by publication year"),
    journal: Optional[str] = Query(None, description="Filter by journal/source"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    sort_by: Optional[str] = Query("created_at", description="Field to sort by"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc")
):
    """
    Get all documents in a specific group with filtering and pagination (optimized).
    """
    # Use the optimized paginated method that queries AI researcher database directly
    result = await document_service.get_paginated_documents_in_group(
        group_id=group_id,
        user_id=current_user.id,
        db=db,
        page=page,
        limit=limit,
        search=search,
        author=author,
        year=year,
        journal=journal,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Convert documents to schema format
    validated_documents = []
    validation_errors = 0
    
    for doc_data in result['documents']:
        try:
            validated_doc = schemas.Document(**doc_data)
            validated_documents.append(validated_doc)
        except Exception as e:
            validation_errors += 1
            if validation_errors <= 5:  # Only print first 5 errors
                logger.debug(f"Validation error for group document: {e}")
                logger.debug(f"Document data: {doc_data}")
            continue
    
    logger.debug(f"API DEBUG: {len(validated_documents)} group documents passed validation, {validation_errors} failed")
    
    # Create pagination info from service result
    pagination_info = schemas.PaginationInfo(
        total_count=result['pagination']['total_count'],
        page=result['pagination']['page'],
        limit=result['pagination']['limit'],
        total_pages=result['pagination']['total_pages'],
        has_next=result['pagination']['has_next'],
        has_previous=result['pagination']['has_previous']
    )
    
    logger.debug(f"API DEBUG: Group documents - Total: {result['pagination']['total_count']}, Page: {page}, Returning: {len(validated_documents)} documents")
    
    return schemas.PaginatedDocumentResponse(
        documents=validated_documents,
        pagination=pagination_info,
        filters_applied=result['filters_applied']
    )

# Document Groups Endpoints

@router.post("/document-groups/", response_model=schemas.DocumentGroup, status_code=201)
def create_document_group(
    group: schemas.DocumentGroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Create a new document group.
    """
    group_id = str(uuid.uuid4())
    return crud.create_document_group(
        db=db,
        group_id=group_id,
        user_id=current_user.id,
        name=group.name,
        description=group.description
    )

@router.get("/document-groups/", response_model=List[schemas.DocumentGroupWithCount])
async def read_user_document_groups(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Retrieve all document groups for the current user with document counts.
    """
    groups = crud.get_user_document_groups(db, user_id=current_user.id, skip=skip, limit=limit)
    
    # Convert to groups with counts
    groups_with_counts = []
    for group in groups:
        # Manually convert metadata to dict to avoid validation errors
        for doc in group.documents:
            if doc.metadata_:
                doc.metadata_ = dict(doc.metadata_)
        
        # Use database as the source of truth for document count
        document_count = len(group.documents)
        logger.debug(f"DEBUG: Group '{group.name}' (ID: {group.id}) has {document_count} documents in database")
        
        # Debug: List the document IDs in this group
        # if group.name == "Papers":
        #     # logger.debug(f"DEBUG: Papers group document IDs: {[doc.id for doc in group.documents]}")
        
        group_with_count = schemas.DocumentGroupWithCount(
            id=group.id,
            name=group.name,
            user_id=group.user_id,
            created_at=group.created_at,
            updated_at=group.updated_at,
            description=group.description,
            documents=group.documents,
            document_count=document_count
        )
        groups_with_counts.append(group_with_count)
    
    return groups_with_counts

@router.get("/document-groups/{group_id}", response_model=schemas.DocumentGroup)
def read_document_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Retrieve a specific document group by its ID.
    """
    db_group = crud.get_document_group(db, group_id=group_id, user_id=current_user.id)
    if db_group is None:
        raise HTTPException(status_code=404, detail="Document group not found")
    return db_group

@router.put("/document-groups/{group_id}", response_model=schemas.DocumentGroup)
def update_document_group(
    group_id: str,
    group: schemas.DocumentGroupUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Update a document group's name and description.
    """
    db_group = crud.update_document_group(
        db,
        group_id=group_id,
        user_id=current_user.id,
        name=group.name,
        description=group.description
    )
    if db_group is None:
        raise HTTPException(status_code=404, detail="Document group not found")
    return db_group

@router.delete("/document-groups/{group_id}", status_code=204)
def delete_document_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Delete a document group by its ID.
    """
    success = crud.delete_document_group(db, group_id=group_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document group not found")
    return

@router.post("/document-groups/{group_id}/documents/{doc_id}", response_model=schemas.DocumentGroup)
def add_document_to_group(
    group_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Add a document to a document group.
    """
    db_group = crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
    if db_group is None:
        raise HTTPException(status_code=404, detail="Document group or document not found")
    return db_group

@router.delete("/document-groups/{group_id}/documents/{doc_id}", response_model=schemas.DocumentGroup)
def remove_document_from_group(
    group_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Remove a document from a document group.
    """
    db_group = crud.remove_document_from_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
    if db_group is None:
        raise HTTPException(status_code=404, detail="Document group or document not found, or document not in group")
    return db_group

# Documents Endpoints

@router.get("/documents/", response_model=List[schemas.Document])
def read_user_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Retrieve all documents for the current user.
    """
    documents = crud.get_user_documents(db, user_id=current_user.id, skip=skip, limit=limit)
    return documents

@router.get("/documents/{doc_id}", response_model=schemas.Document)
def read_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Retrieve a specific document by its ID.
    """
    db_document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
    if db_document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return db_document

@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Delete a document by its ID (unified ID system - deletes from all storage systems).
    """
    # Use document service directly to avoid async issues
    try:
        # Delete from vector stores and AI researcher database
        vector_success = await document_service.delete_document_completely(doc_id, current_user.id, db)
        
        # Delete from main database
        db_success = crud.delete_document_simple_sync(db, doc_id=doc_id, user_id=current_user.id)
        
        # Return success if deleted from any system
        if vector_success or db_success:
            logger.info(f"Document {doc_id} deleted - Vector/AI DB: {vector_success}, Main DB: {db_success}")
            return
        else:
            raise HTTPException(status_code=404, detail="Document not found in any storage system")
            
    except Exception as e:
        logger.error(f"Error deleting document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")

# Bulk operations endpoints
@router.post("/documents/bulk-delete", status_code=204)
async def bulk_delete_documents(
    document_ids: List[str],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Delete multiple documents by their IDs from all storage systems.
    """
    deleted_count = 0
    failed_deletions = []
    
    for doc_id in document_ids:
        try:
            # Delete from vector stores and AI researcher database
            vector_success = await document_service.delete_document_completely(doc_id, current_user.id, db)
            
            # Delete from main database
            db_success = crud.delete_document_simple_sync(db, doc_id=doc_id, user_id=current_user.id)
            
            # Count as success if deleted from any system
            if vector_success or db_success:
                deleted_count += 1
                logger.info(f"Document {doc_id} deleted - Vector/AI DB: {vector_success}, Main DB: {db_success}")
            else:
                failed_deletions.append(doc_id)
                
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            failed_deletions.append(doc_id)
    
    if failed_deletions:
        raise HTTPException(
            status_code=207,  # Multi-status
            detail=f"Deleted {deleted_count} documents. Failed to delete: {failed_deletions}"
        )
    
    return

@router.post("/document-groups/{group_id}/bulk-add-documents")
async def bulk_add_documents_to_group(
    group_id: str,
    document_ids: List[str],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Add multiple existing documents to a group.
    """
    added_count = 0
    failed_additions = []
    
    for doc_id in document_ids:
        try:
            success = await document_service.add_document_to_group(group_id, doc_id, current_user.id, db)
            if success:
                added_count += 1
            else:
                failed_additions.append(doc_id)
        except Exception as e:
            logger.debug(f"Error adding document {doc_id} to group: {e}")
            failed_additions.append(doc_id)
    
    return {
        "added_count": added_count,
        "failed_additions": failed_additions,
        "message": f"Added {added_count} documents to group"
    }

@router.post("/document-groups/{group_id}/bulk-remove-documents")
async def bulk_remove_documents_from_group(
    group_id: str,
    document_ids: List[str],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Remove multiple documents from a group.
    """
    removed_count = 0
    failed_removals = []
    
    for doc_id in document_ids:
        try:
            db_group = crud.remove_document_from_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
            if db_group:
                removed_count += 1
            else:
                failed_removals.append(doc_id)
        except Exception as e:
            logger.debug(f"Error removing document {doc_id} from group: {e}")
            failed_removals.append(doc_id)
    
    return {
        "removed_count": removed_count,
        "failed_removals": failed_removals,
        "message": f"Removed {removed_count} documents from group"
    }

# Document Metadata and Content endpoints
@router.put("/documents/{doc_id}/metadata", response_model=schemas.Document)
async def update_document_metadata(
    doc_id: str,
    metadata_update: schemas.DocumentMetadataUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Update document metadata across all databases (Main DB, AI DB, Vector Store).
    """
    try:
        updated_document = await document_service.update_document_metadata(
            doc_id=doc_id,
            user_id=current_user.id,
            metadata_update=metadata_update.dict(exclude_unset=True),
            db=db
        )
        
        if not updated_document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Send websocket update for real-time UI updates
        await send_document_update(str(current_user.id), {
            "type": "metadata_updated",
            "doc_id": doc_id,
            "status": "metadata_updated",
            "metadata": updated_document.get("metadata_", {})
        })
        
        return schemas.Document(**updated_document)
        
    except Exception as e:
        logger.error(f"Error updating metadata for document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update document metadata")

@router.get("/documents/{doc_id}/view", response_model=schemas.DocumentViewResponse)
async def view_document_content(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Get document content for viewing (includes markdown content and metadata).
    """
    try:
        document_data = await document_service.get_document_content(
            doc_id=doc_id,
            user_id=current_user.id,
            db=db
        )
        
        if not document_data:
            raise HTTPException(status_code=404, detail="Document not found or no content available")
            
        return schemas.DocumentViewResponse(**document_data)
        
    except Exception as e:
        logger.error(f"Error retrieving content for document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document content")

@router.post("/documents/{doc_id}/cancel", status_code=200)
async def cancel_document_processing(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Cancel document processing for a specific document.
    """
    try:
        # Update document status to cancelled in database
        success = await document_service.cancel_document_processing(doc_id, current_user.id, db)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or cannot be cancelled")
        
        # Send cancellation update via WebSocket
        await send_document_update(str(current_user.id), {
            "type": "document_progress",
            "doc_id": doc_id,
            "document_id": doc_id,
            "progress": 0,
            "status": "cancelled",
            "error": "Cancelled by user",
            "user_id": str(current_user.id),
            "timestamp": str(datetime.utcnow())
        })
        
        return {"message": "Document processing cancelled successfully"}
    except Exception as e:
        logger.debug(f"Error cancelling document processing: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel document processing")

# Note: The following endpoint is for internal use by the doc-processor service
@router.post("/internal/document-progress", status_code=202, include_in_schema=False)
async def post_document_progress(update: schemas.DocumentProgressUpdate):
    """
    Internal endpoint for the document processor to post progress updates.
    These updates are then broadcast to the relevant user via WebSockets.
    """
    try:
        logger.debug(f"Received progress update: {update.dict()}")
        await send_document_update(str(update.user_id), update.dict())
        logger.debug(f"Successfully sent document update to user {update.user_id}")
        return {"status": "update accepted"}
    except Exception as e:
        # Log the error but don't crash the service
        logger.debug(f"Error broadcasting document update: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "update failed"}
