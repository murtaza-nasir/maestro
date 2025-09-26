import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from database import crud, models
from api import schemas
from auth.dependencies import get_current_user_from_cookie
from database.database import get_db
from services.document_service_v2 import UnifiedDocumentService
import json
from api.websockets import send_document_update
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Documents Endpoints

# Get all documents endpoint - must come before {doc_id} route
@router.get("/documents/all", response_model=schemas.PaginatedDocumentResponse)
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
    # Initialize document service with current db session
    document_service = UnifiedDocumentService(db)
    
    # Get documents with metadata from the unified database
    documents, total_count = document_service.get_documents_with_metadata(
        user_id=current_user.id,
        search=search,
        author=author,
        year=year,
        journal=journal,
        status_filter=status,
        limit=limit,
        offset=(page - 1) * limit
    )
    
    # Convert documents to schema format
    validated_documents = []
    validation_errors = 0
    
    for i, doc in enumerate(documents):
        try:
            # Ensure metadata_ field is properly formatted
            if 'metadata_' not in doc and any(k in doc for k in ['abstract', 'keywords', 'doi']):
                doc['metadata_'] = {
                    'title': doc.get('title'),
                    'authors': doc.get('authors', []),
                    'publication_year': doc.get('publication_year'),
                    'journal_or_source': doc.get('journal'),
                    'abstract': doc.get('abstract'),
                    'keywords': doc.get('keywords', []),
                    'doi': doc.get('doi')
                }
            validated_doc = schemas.Document(**doc)
            validated_documents.append(validated_doc)
        except Exception as e:
            validation_errors += 1
            if validation_errors <= 5:  # Only print first 5 errors
                logger.debug(f"API DEBUG: Validation error for document {i}: {e}")
                logger.debug(f"API DEBUG: Document data: {doc}")
    
    logger.debug(f"API DEBUG: {len(validated_documents)} documents passed validation, {validation_errors} failed")
    
    # Calculate pagination info
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
    pagination_info = schemas.PaginationInfo(
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1
    )
    
    logger.debug(f"API DEBUG: Filtered to {total_count} documents, returning page {page} with {len(validated_documents)} items")
    
    return schemas.PaginatedDocumentResponse(
        documents=validated_documents,
        pagination=pagination_info,
        filters_applied={
            'search': search,
            'author': author,
            'year': year,
            'journal': journal,
            'status': status
        }
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
    document_service = UnifiedDocumentService(db)
    results = document_service.semantic_search(query, current_user.id, n_results)
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
    # For now, just add document directly to the group
    group_doc = crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
    if not group_doc:
        raise HTTPException(status_code=404, detail="Document not found or could not be added to group")
    return {"message": "Document added to group successfully"}

# Upload document without group (to user's general documents)
@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Upload a new document to user's general documents (no group).
    """
    # Check for supported file formats
    filename_lower = file.filename.lower()
    supported_extensions = ['.pdf', '.docx', '.doc', '.md', '.markdown']
    
    if not any(filename_lower.endswith(ext) for ext in supported_extensions):
        raise HTTPException(
            status_code=400, 
            detail="Only PDF, Word (docx, doc), and Markdown (md, markdown) files are supported"
        )
    
    try:
        import uuid
        import os
        import hashlib
        from datetime import datetime
        
        # Read file content
        file_content = await file.read()
        
        # Generate document ID
        doc_id = str(uuid.uuid4())
        
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256(file_content).hexdigest()
        logger.info(f"Calculated file hash for {file.filename}: {file_hash}")
        
        # Check if document already exists (by hash)
        existing = db.query(models.Document).filter(
            models.Document.user_id == current_user.id,
            models.Document.metadata_.op('->>')('file_hash') == file_hash
        ).first()
        
        if existing:
            logger.info(f"Found existing document with same hash: {existing.id} - {existing.filename}")
        
        if existing:
            # Document already exists, return with 409 Conflict status
            return JSONResponse(
                status_code=409,
                content={
                    "id": str(existing.id),
                    "filename": existing.filename,
                    "status": "duplicate",
                    "processing_status": existing.processing_status,
                    "message": f"This document has already been uploaded: {existing.filename}",
                    "duplicate": True,
                    "existing_document_id": str(existing.id)
                }
            )
        
        # Save the file to disk
        upload_dir = "/app/data/raw_files"
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, f"{doc_id}_{file.filename}")
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Create document record in database
        metadata = {
            "title": file.filename,
            "file_hash": file_hash,
            "upload_timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Creating document with metadata: {metadata}")
        
        new_document = models.Document(
            id=doc_id,
            user_id=current_user.id,
            filename=file.filename,
            original_filename=file.filename,
            metadata_=metadata,
            processing_status="pending",
            file_size=len(file_content),
            file_path=file_path,
            raw_file_path=file_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_document)
        db.commit()
        db.refresh(new_document)
        
        # Trigger document processing (send to background processor)
        from api.websockets import send_document_update
        await send_document_update(str(current_user.id), {
            "type": "document_uploaded",
            "doc_id": doc_id,
            "status": "pending",
            "filename": file.filename
        })
        
        # Document is already created with "pending" status
        # The background processor will pick it up automatically
        logger.info(f"Document {doc_id} created with pending status, will be processed by background service")
        
        return {
            "id": doc_id,
            "filename": file.filename,
            "status": "processing",
            "processing_status": "pending",
            "message": "Document uploaded and processing started",
            "duplicate": False
        }
        
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

# New endpoint to upload and process documents to a specific group
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
    
    try:
        import uuid
        import os
        import hashlib
        from datetime import datetime
        
        # Read file content
        file_content = await file.read()
        
        # Generate document ID
        doc_id = str(uuid.uuid4())
        
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256(file_content).hexdigest()
        logger.info(f"Calculated file hash for {file.filename}: {file_hash}")
        
        # Check if document already exists (by hash)
        existing = db.query(models.Document).filter(
            models.Document.user_id == current_user.id,
            models.Document.metadata_.op('->>')('file_hash') == file_hash
        ).first()
        
        if existing:
            logger.info(f"Found existing document with same hash: {existing.id} - {existing.filename}")
        
        if existing:
            # Document already exists, just add to group if not already there
            # Check if already in group
            from sqlalchemy import and_
            existing_in_group = db.query(models.DocumentGroupAssociation).filter(
                and_(
                    models.DocumentGroupAssociation.document_id == existing.id,
                    models.DocumentGroupAssociation.document_group_id == group_id
                )
            ).first()
            
            if existing_in_group:
                # Already in this group
                return JSONResponse(
                    status_code=409,
                    content={
                        "id": str(existing.id),
                        "filename": existing.filename,
                        "status": "duplicate",
                        "processing_status": existing.processing_status,
                        "message": f"Document '{existing.filename}' already exists in this group",
                        "duplicate": True,
                        "existing_document_id": str(existing.id)
                    }
                )
            else:
                # Add to group
                crud.add_document_to_group(db, group_id=group_id, doc_id=str(existing.id), user_id=current_user.id)
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": str(existing.id),
                        "filename": existing.filename,
                        "status": "existing",
                        "processing_status": existing.processing_status,
                        "message": f"Existing document '{existing.filename}' was added to the group",
                        "duplicate": False,
                        "existing_document_id": str(existing.id)
                    }
                )
        
        # Save the file to disk
        upload_dir = "/app/data/raw_files"
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, f"{doc_id}_{file.filename}")
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Create document record in database
        metadata = {
            "title": file.filename,
            "file_hash": file_hash,
            "upload_timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Creating document with metadata: {metadata}")
        
        new_document = models.Document(
            id=doc_id,
            user_id=current_user.id,
            filename=file.filename,
            original_filename=file.filename,
            metadata_=metadata,
            processing_status="pending",
            file_size=len(file_content),
            file_path=file_path,
            raw_file_path=file_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_document)
        db.commit()
        db.refresh(new_document)
        
        # Add document to group
        crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
        
        # Trigger document processing (send to background processor)
        from api.websockets import send_document_update
        await send_document_update(str(current_user.id), {
            "type": "document_uploaded",
            "doc_id": doc_id,
            "status": "pending",
            "filename": file.filename
        })
        
        # Document is already created with "pending" status
        # The background processor will pick it up automatically
        logger.info(f"Document {doc_id} created with pending status, will be processed by background service")
        
        return {
            "id": doc_id,
            "filename": file.filename,
            "status": "processing",
            "processing_status": "pending",
            "message": "Document uploaded and processing started",
            "duplicate": False
        }
        
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

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
    # Initialize document service and get documents in group
    document_service = UnifiedDocumentService(db)
    documents, total_count = document_service.get_documents_with_metadata(
        user_id=current_user.id,
        search=search,
        author=author,
        year=year,
        journal=journal,
        status_filter=status,
        group_id=group_id,
        limit=limit,
        offset=(page - 1) * limit
    )
    
    # Convert documents to schema format
    validated_documents = []
    validation_errors = 0
    
    for doc_data in documents:
        try:
            # Ensure metadata_ field is properly formatted
            if 'metadata_' not in doc_data and any(k in doc_data for k in ['abstract', 'keywords', 'doi']):
                doc_data['metadata_'] = {
                    'title': doc_data.get('title'),
                    'authors': doc_data.get('authors', []),
                    'publication_year': doc_data.get('publication_year'),
                    'journal_or_source': doc_data.get('journal'),
                    'abstract': doc_data.get('abstract'),
                    'keywords': doc_data.get('keywords', []),
                    'doi': doc_data.get('doi')
                }
            validated_doc = schemas.Document(**doc_data)
            validated_documents.append(validated_doc)
        except Exception as e:
            validation_errors += 1
            if validation_errors <= 5:  # Only print first 5 errors
                logger.debug(f"Validation error for group document: {e}")
                logger.debug(f"Document data: {doc_data}")
            continue
    
    logger.debug(f"API DEBUG: {len(validated_documents)} group documents passed validation, {validation_errors} failed")
    
    # Calculate pagination info
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
    pagination_info = schemas.PaginationInfo(
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1
    )
    
    logger.debug(f"API DEBUG: Group documents - Total: {total_count}, Page: {page}, Returning: {len(validated_documents)} documents")
    
    return schemas.PaginatedDocumentResponse(
        documents=validated_documents,
        pagination=pagination_info,
        filters_applied={
            'search': search,
            'author': author,
            'year': year,
            'journal': journal,
            'status': status,
            'group_id': group_id
        }
    )

# New endpoint to get filter options
@router.get("/documents/filter-options", response_model=dict)
async def get_filter_options(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
    group_id: Optional[str] = Query(None, description="Optional group ID to filter options")
):
    """
    Get available filter options (authors, years, journals) from user's documents.
    """
    try:
        from sqlalchemy import distinct, func
        
        # Base query for user's documents
        query = db.query(models.Document).filter(models.Document.user_id == current_user.id)
        
        # If group_id provided, filter to documents in that group
        if group_id:
            query = query.join(
                models.document_group_association,
                models.Document.id == models.document_group_association.c.document_id
            ).filter(models.document_group_association.c.document_group_id == group_id)
        
        # Get all documents for this user/group
        documents = query.all()
        logger.info(f"Found {len(documents)} documents for filter options")
        
        # Extract unique values from metadata
        authors = set()
        years = set()
        journals = set()
        
        for doc in documents:
            logger.debug(f"Processing doc {doc.id}: metadata={doc.metadata_}")
            if doc.metadata_:
                # Extract authors
                doc_authors = doc.metadata_.get('authors', [])
                if isinstance(doc_authors, list):
                    # Filter out None values before adding
                    authors.update([a for a in doc_authors if a is not None])
                elif isinstance(doc_authors, str):
                    try:
                        parsed = json.loads(doc_authors)
                        if isinstance(parsed, list):
                            # Filter out None values from parsed list
                            authors.update([a for a in parsed if a is not None])
                        else:
                            authors.add(doc_authors)
                    except:
                        if doc_authors:
                            authors.add(doc_authors)
                
                # Extract year
                year = doc.metadata_.get('publication_year')
                if year:
                    try:
                        years.add(int(year))
                    except (ValueError, TypeError):
                        logger.debug(f"Could not convert year to int: {year}")
                
                # Extract journal
                journal = doc.metadata_.get('journal_or_source')
                if journal and journal is not None:
                    journals.add(journal)
        
        # Filter out None values before sorting
        return {
            "authors": sorted([a for a in authors if a is not None]),
            "years": sorted(list(years), reverse=True),
            "journals": sorted([j for j in journals if j is not None])
        }
        
    except Exception as e:
        logger.error(f"Error getting filter options: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get filter options: {str(e)}")

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

@router.get("/document-groups/", response_model=List[schemas.DocumentGroupSummary])
async def read_user_document_groups(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Retrieve all document groups for the current user with document counts.
    Returns lightweight summaries without document data to reduce payload size.
    """
    # Get groups without eager loading documents
    query = db.query(models.DocumentGroup).filter_by(user_id=current_user.id)
    groups = query.offset(skip).limit(limit).all()
    
    # Convert to lightweight summaries
    group_summaries = []
    for group in groups:
        # Count documents efficiently without loading their data
        document_count = db.query(models.document_group_association).filter_by(
            document_group_id=group.id
        ).count()
        
        group_summary = schemas.DocumentGroupSummary(
            id=group.id,
            name=group.name,
            description=group.description,
            document_count=document_count,
            created_at=group.created_at,
            updated_at=group.updated_at
        )
        group_summaries.append(group_summary)
    
    return group_summaries

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
        # Initialize service and delete document
        document_service = UnifiedDocumentService(db)
        vector_success = await document_service.delete_document_with_cascade(doc_id, current_user.id)
        
        # Delete from main database using async CRUD
        from database.database import get_async_db
        from database import async_crud
        
        async with get_async_db() as async_db:
            db_success = await async_crud.delete_document(async_db, doc_id=doc_id, user_id=current_user.id)
        
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
    
    # Import here to avoid circular dependencies
    from database.crud_documents_improved import delete_document_atomically_sync
    
    for doc_id in document_ids:
        try:
            # Call the synchronous version directly
            success = delete_document_atomically_sync(db, doc_id, current_user.id)
            
            if success:
                deleted_count += 1
                logger.info(f"Document {doc_id} deleted successfully")
            else:
                failed_deletions.append(doc_id)
                logger.warning(f"Failed to delete document {doc_id}")
                
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            import traceback
            traceback.print_exc()
            failed_deletions.append(doc_id)
            # Continue with other deletions
    
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
    try:
        # For now, just add documents directly to the group without checking vector store
        # This avoids the crash issue with vector store initialization
        added_count = 0
        failed_additions = []
        
        for doc_id in document_ids:
            try:
                # Check if document exists in database
                document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
                if document:
                    # Add to group
                    group_doc = crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=current_user.id)
                    if group_doc:
                        added_count += 1
                    else:
                        failed_additions.append(doc_id)
                else:
                    logger.warning(f"Document {doc_id} not found for user {current_user.id}")
                    failed_additions.append(doc_id)
            except Exception as e:
                logger.error(f"Error adding document {doc_id} to group: {e}")
                failed_additions.append(doc_id)
        
        return {
            "added_count": added_count,
            "failed_additions": failed_additions,
            "message": f"Added {added_count} documents to group"
        }
    except Exception as e:
        logger.error(f"Critical error in bulk_add_documents_to_group: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
        # For now, update metadata directly in the database
        # The document service needs proper async implementation
        document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get existing metadata or create new
        existing_metadata = document.metadata_ or {}
        
        # Update metadata fields in JSONB
        update_data = metadata_update.dict(exclude_unset=True)
        
        # Build updated metadata
        updated_metadata = existing_metadata.copy()
        
        if 'title' in update_data:
            updated_metadata['title'] = update_data['title']
        if 'authors' in update_data:
            updated_metadata['authors'] = update_data['authors']
        if 'publication_year' in update_data:
            updated_metadata['publication_year'] = update_data['publication_year']
        if 'journal_or_source' in update_data:
            updated_metadata['journal_or_source'] = update_data['journal_or_source']
        if 'abstract' in update_data:
            updated_metadata['abstract'] = update_data['abstract']
        if 'keywords' in update_data:
            updated_metadata['keywords'] = update_data['keywords']
        if 'doi' in update_data:
            updated_metadata['doi'] = update_data['doi']
        
        # Update document's metadata_ field
        document.metadata_ = updated_metadata
        
        db.commit()
        db.refresh(document)
        
        # Prepare response with proper JSON encoding for schema
        authors = updated_metadata.get('authors', [])
        if isinstance(authors, list):
            authors_str = json.dumps(authors) if authors else None
        else:
            authors_str = authors
            
        keywords = updated_metadata.get('keywords', [])
        if isinstance(keywords, list):
            keywords_str = json.dumps(keywords) if keywords else None
        else:
            keywords_str = keywords
        
        updated_document = {
            'id': document.id,
            'user_id': current_user.id,
            'filename': document.filename,
            'original_filename': document.original_filename,
            'title': updated_metadata.get('title', document.original_filename),
            'authors': authors_str,
            'publication_year': updated_metadata.get('publication_year'),
            'journal': updated_metadata.get('journal_or_source'),
            'abstract': updated_metadata.get('abstract'),
            'doi': updated_metadata.get('doi'),
            'keywords': keywords_str,
            'processing_status': document.processing_status,
            'processing_error': document.processing_error,
            'upload_progress': document.upload_progress,
            'chunk_count': document.chunk_count,
            'file_size': document.file_size,
            'created_at': document.created_at.isoformat() if document.created_at else None,
            'updated_at': document.updated_at.isoformat() if document.updated_at else None,
            'metadata_': updated_metadata
        }
        
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
        document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Extract metadata from JSONB field
        metadata = document.metadata_ or {}
        title = metadata.get('title') or document.original_filename or document.filename
        
        # Parse authors and keywords if they're stored as strings
        authors = metadata.get('authors', [])
        if isinstance(authors, str):
            try:
                authors = json.loads(authors)
            except:
                authors = [authors]
        
        keywords = metadata.get('keywords', [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except:
                keywords = [keywords]
        
        # Try to read the markdown content from file
        markdown_content = None
        markdown_path = f"/app/ai_researcher/data/processed/markdown/{doc_id}.md"
        
        try:
            import os
            if os.path.exists(markdown_path):
                with open(markdown_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                logger.info(f"Successfully loaded markdown content for document {doc_id}")
            else:
                # Try alternative path
                alt_markdown_path = f"/app/data/markdown_files/{doc_id}.md"
                if os.path.exists(alt_markdown_path):
                    with open(alt_markdown_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()
                    logger.info(f"Successfully loaded markdown content from alternative path for document {doc_id}")
                else:
                    logger.warning(f"Markdown file not found for document {doc_id} at {markdown_path} or {alt_markdown_path}")
        except Exception as e:
            logger.error(f"Error reading markdown file for document {doc_id}: {e}")
        
        # Fallback if no markdown content found
        if not markdown_content:
            markdown_content = f"# {title}\n\n*Document content is being processed or not available.*"
        
        document_data = {
            'id': document.id,
            'original_filename': document.original_filename or document.filename,
            'title': title,
            'content': markdown_content,  # Use actual markdown content
            'metadata_': metadata,  # Use the full metadata object
            'created_at': document.created_at.isoformat() if document.created_at else None,
            'file_size': document.file_size
        }
            
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
        document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if document.processing_status == 'processing':
            document.processing_status = 'cancelled'
            db.commit()
            success = True
        else:
            success = False
        
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

@router.post("/documents/bulk-reprocess", response_model=schemas.BulkOperationResponse)
async def bulk_reprocess_documents(
    request: schemas.BulkDocumentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Reprocess documents (extract metadata only, without re-embedding).
    This will update the metadata extraction for the selected documents.
    """
    try:
        doc_ids = request.document_ids
        logger.info(f"User {current_user.id} requested reprocessing for {len(doc_ids)} documents")
        
        success_count = 0
        failed_count = 0
        failed_docs = []
        
        for doc_id in doc_ids:
            try:
                # Get the document
                document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
                if not document:
                    failed_count += 1
                    failed_docs.append({"id": doc_id, "error": "Document not found"})
                    continue
                
                # Reset the document status to pending for reprocessing
                document.processing_status = "pending"
                document.metadata_['reprocess_metadata'] = True  # Flag for processor to only do metadata
                db.commit()
                
                # Send update via WebSocket
                await send_document_update(str(current_user.id), {
                    "type": "document_reprocess_started",
                    "doc_id": doc_id,
                    "status": "pending",
                    "message": "Document queued for metadata reprocessing"
                })
                
                success_count += 1
                logger.info(f"Document {doc_id} queued for metadata reprocessing")
                
            except Exception as e:
                failed_count += 1
                failed_docs.append({"id": doc_id, "error": str(e)})
                logger.error(f"Failed to queue document {doc_id} for reprocessing: {e}")
        
        return schemas.BulkOperationResponse(
            success_count=success_count,
            failed_count=failed_count,
            failed_items=failed_docs,
            message=f"Queued {success_count} documents for metadata reprocessing"
        )
        
    except Exception as e:
        logger.error(f"Error in bulk_reprocess_documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/bulk-reembed", response_model=schemas.BulkOperationResponse)  
async def bulk_reembed_documents(
    request: schemas.BulkDocumentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Re-embed documents (full reprocessing including metadata extraction and embeddings).
    This will delete existing embeddings and create new ones.
    """
    try:
        doc_ids = request.document_ids
        logger.info(f"User {current_user.id} requested re-embedding for {len(doc_ids)} documents")
        
        success_count = 0
        failed_count = 0
        failed_docs = []
        
        # Import vector store to delete existing embeddings
        from ai_researcher.core_rag.vector_store_singleton import get_vector_store
        vector_store = get_vector_store()
        
        for doc_id in doc_ids:
            try:
                # Get the document
                document = crud.get_document(db, doc_id=doc_id, user_id=current_user.id)
                if not document:
                    failed_count += 1
                    failed_docs.append({"id": doc_id, "error": "Document not found"})
                    continue
                
                # Delete existing embeddings from vector store
                try:
                    dense_deleted, sparse_deleted = vector_store.delete_document(doc_id)
                    logger.info(f"Deleted {dense_deleted + sparse_deleted} existing chunks for document {doc_id}")
                except Exception as e:
                    logger.warning(f"Error deleting existing embeddings for {doc_id}: {e}")
                
                # Reset document status and clear chunk count
                document.processing_status = "pending"
                document.chunk_count = 0
                document.metadata_['reembed'] = True  # Flag for processor to do full reprocessing
                db.commit()
                
                # Send update via WebSocket
                await send_document_update(str(current_user.id), {
                    "type": "document_reembed_started",
                    "doc_id": doc_id,
                    "status": "pending",
                    "message": "Document queued for full re-embedding"
                })
                
                success_count += 1
                logger.info(f"Document {doc_id} queued for re-embedding")
                
            except Exception as e:
                failed_count += 1
                failed_docs.append({"id": doc_id, "error": str(e)})
                logger.error(f"Failed to queue document {doc_id} for re-embedding: {e}")
        
        return schemas.BulkOperationResponse(
            success_count=success_count,
            failed_count=failed_count,
            failed_items=failed_docs,
            message=f"Queued {success_count} documents for full re-embedding"
        )
        
    except Exception as e:
        logger.error(f"Error in bulk_reembed_documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
