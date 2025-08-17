"""
PostgreSQL-based Vector Store using pgvector

This implementation uses PostgreSQL with the pgvector extension for all vector operations.
Benefits over ChromaDB + PostgreSQL hybrid:
- Single database for all data (simpler architecture)
- ACID transactions across all operations
- No synchronization issues
- Native vector similarity search with HNSW indexing
- Efficient storage for both dense (1024-dim) and sparse embeddings
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text, select, and_
import json

# Import database components
from database.database import get_db
from database.models import DocumentChunk

logger = logging.getLogger(__name__)

# Constants for embedding dimensions
DENSE_DIMENSION = 1024  # BGE-M3 dense embeddings


class PGVectorStore:
    """
    PostgreSQL-based vector store using pgvector extension.
    Stores both dense and sparse embeddings efficiently in a single database.
    """
    
    def __init__(self):
        """Initialize the PostgreSQL vector store."""
        logger.info("Initializing PGVectorStore")
        
        # Test pgvector availability
        self._check_pgvector()
        logger.info("PGVectorStore initialized successfully")
    
    def _check_pgvector(self):
        """Check if pgvector extension is available."""
        db = next(get_db())
        try:
            result = db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
            version = result.fetchone()
            if version:
                logger.info(f"pgvector extension found, version: {version[0]}")
            else:
                logger.error("pgvector extension not found. Please install it.")
                raise RuntimeError("pgvector extension not installed")
        except Exception as e:
            logger.error(f"Error checking pgvector: {e}")
            raise
        finally:
            db.close()
    
    def add_chunks(
        self,
        doc_id: str,
        chunks: List[Dict[str, Any]],
        dense_embeddings: List[np.ndarray],
        sparse_embeddings: List[Dict[int, float]],
        batch_size: int = 100
    ) -> Tuple[int, int]:
        """
        Add document chunks with embeddings to PostgreSQL.
        
        Args:
            doc_id: Document ID
            chunks: List of chunk dictionaries with text and metadata
            dense_embeddings: List of dense embedding vectors (1024-dim)
            sparse_embeddings: List of sparse embedding dictionaries
            batch_size: Number of chunks to insert in each batch
            
        Returns:
            Tuple of (chunks_added, chunks_added) for compatibility
        """
        if not chunks:
            logger.warning(f"No chunks to add for document {doc_id}")
            return 0, 0
        
        chunks_added = 0
        total_chunks = len(chunks)
        
        db = next(get_db())
        
        try:
            # Process chunks in batches
            for batch_start in range(0, total_chunks, batch_size):
                batch_end = min(batch_start + batch_size, total_chunks)
                batch_chunks = chunks[batch_start:batch_end]
                batch_dense = dense_embeddings[batch_start:batch_end]
                batch_sparse = sparse_embeddings[batch_start:batch_end]
                
                for i, chunk in enumerate(batch_chunks):
                    chunk_index = batch_start + i
                    chunk_id = f"{doc_id}_{chunk_index}"
                    
                    # Extract text and metadata
                    if isinstance(chunk, dict):
                        chunk_text = chunk.get('text', '')
                        chunk_metadata = chunk.get('metadata', {})
                    else:
                        chunk_text = str(chunk)
                        chunk_metadata = {}
                    
                    # Prepare dense embedding
                    dense_embedding = batch_dense[i]
                    if isinstance(dense_embedding, np.ndarray):
                        # Convert to list for PostgreSQL
                        dense_embedding = dense_embedding.tolist()
                    
                    # Prepare sparse embedding
                    sparse_dict = batch_sparse[i]
                    # Convert integer keys to strings and numpy float32 to Python float
                    sparse_json = {str(k): float(v) for k, v in sparse_dict.items()}
                    
                    # Check if chunk already exists
                    existing = db.query(DocumentChunk).filter_by(chunk_id=chunk_id).first()
                    
                    if existing:
                        # Update existing chunk
                        existing.chunk_text = chunk_text
                        existing.dense_embedding = dense_embedding
                        existing.sparse_embedding = sparse_json
                        existing.chunk_metadata = chunk_metadata
                        logger.debug(f"Updated existing chunk {chunk_id}")
                    else:
                        # Insert using raw SQL for pgvector support
                        insert_query = text("""
                            INSERT INTO document_chunks 
                            (doc_id, chunk_id, chunk_index, chunk_text, dense_embedding, sparse_embedding, chunk_metadata)
                            VALUES 
                            (:doc_id, :chunk_id, :chunk_index, :chunk_text, CAST(:dense_embedding AS vector), CAST(:sparse_embedding AS jsonb), CAST(:chunk_metadata AS jsonb))
                        """)
                        
                        db.execute(insert_query, {
                            'doc_id': doc_id,
                            'chunk_id': chunk_id,
                            'chunk_index': chunk_index,
                            'chunk_text': chunk_text,
                            'dense_embedding': str(dense_embedding),  # Convert list to string for casting
                            'sparse_embedding': json.dumps(sparse_json),
                            'chunk_metadata': json.dumps(chunk_metadata)
                        })
                        
                    chunks_added += 1
                
                # Commit after each batch
                db.commit()
                logger.debug(f"Added batch of {batch_end - batch_start} chunks to PostgreSQL")
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add chunks: {e}")
            raise
        finally:
            db.close()
        
        logger.info(f"Added {chunks_added} chunks to PostgreSQL for document {doc_id}")
        
        # Return same count for both dense and sparse for compatibility
        return chunks_added, chunks_added
    
    def query(
        self,
        query_dense_embedding: np.ndarray,
        query_sparse_embedding_dict: Dict[int, float],
        n_results: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search using both dense and sparse embeddings.
        
        Args:
            query_dense_embedding: Dense query embedding (1024-dim)
            query_sparse_embedding_dict: Sparse query embedding dictionary
            n_results: Number of results to return
            filter_metadata: Optional metadata filter
            dense_weight: Weight for dense similarity (0-1)
            sparse_weight: Weight for sparse similarity (0-1)
            
        Returns:
            List of search results with metadata
        """
        # Normalize weights
        total_weight = dense_weight + sparse_weight
        if total_weight > 0:
            dense_weight = dense_weight / total_weight
            sparse_weight = sparse_weight / total_weight
        else:
            dense_weight = sparse_weight = 0.5
        
        db = next(get_db())
        
        try:
            # Convert query embedding to list
            if isinstance(query_dense_embedding, np.ndarray):
                query_dense_embedding = query_dense_embedding.tolist()
            
            # Build filter conditions
            where_clauses = []
            if filter_metadata:
                if "doc_id" in filter_metadata:
                    if isinstance(filter_metadata["doc_id"], dict) and "$in" in filter_metadata["doc_id"]:
                        doc_ids = filter_metadata["doc_id"]["$in"]
                        where_clauses.append(f"doc_id = ANY(ARRAY{doc_ids}::uuid[])")
                    else:
                        where_clauses.append(f"doc_id = '{filter_metadata['doc_id']}'")
            
            where_clause = " AND " + " AND ".join(where_clauses) if where_clauses else ""
            
            # Perform hybrid search using PostgreSQL
            # Dense similarity using pgvector's cosine distance operator
            # Note: <=> operator returns distance, so we use 1 - distance for similarity
            # Convert embedding to string format for casting
            embedding_str = str(query_dense_embedding) if isinstance(query_dense_embedding, list) else query_dense_embedding
            
            query = text(f"""
                WITH dense_scores AS (
                    SELECT 
                        chunk_id,
                        doc_id,
                        chunk_text,
                        chunk_metadata,
                        1 - (dense_embedding <=> CAST(:query_embedding AS vector)) as dense_similarity
                    FROM document_chunks
                    WHERE dense_embedding IS NOT NULL {where_clause}
                    ORDER BY dense_embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :limit
                )
                SELECT 
                    chunk_id,
                    doc_id,
                    chunk_text,
                    chunk_metadata,
                    dense_similarity,
                    dense_similarity * :dense_weight as weighted_score
                FROM dense_scores
                ORDER BY weighted_score DESC
                LIMIT :n_results
            """)
            
            results = db.execute(query, {
                'query_embedding': embedding_str,
                'limit': n_results * 2,  # Get more for potential filtering
                'n_results': n_results,
                'dense_weight': dense_weight
            }).fetchall()
            
            # Format results
            formatted_results = []
            for row in results:
                formatted_results.append({
                    'id': row.chunk_id,
                    'doc_id': row.doc_id,
                    'text': row.chunk_text,
                    'metadata': row.chunk_metadata if row.chunk_metadata else {},
                    'score': float(row.weighted_score)
                })
            
            # If sparse weight > 0, also compute sparse similarity and merge
            if sparse_weight > 0 and query_sparse_embedding_dict:
                sparse_results = self._query_sparse(
                    db, query_sparse_embedding_dict, n_results * 2, where_clause
                )
                
                # Merge results
                merged = {}
                for result in formatted_results:
                    merged[result['id']] = result
                
                for sparse_result in sparse_results:
                    chunk_id = sparse_result['id']
                    sparse_score = sparse_result['score'] * sparse_weight
                    
                    if chunk_id in merged:
                        merged[chunk_id]['score'] += sparse_score
                    else:
                        sparse_result['score'] = sparse_score
                        merged[chunk_id] = sparse_result
                
                # Sort by combined score
                formatted_results = sorted(
                    merged.values(), 
                    key=lambda x: x['score'], 
                    reverse=True
                )[:n_results]
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
        finally:
            db.close()
    
    def _query_sparse(
        self,
        db: Session,
        query_sparse_dict: Dict[int, float],
        n_results: int,
        where_clause: str
    ) -> List[Dict[str, Any]]:
        """
        Query sparse embeddings using cosine similarity.
        This is computed in Python for now, but could be optimized with a PL/pgSQL function.
        """
        # Get chunks with sparse embeddings
        query = text(f"""
            SELECT 
                chunk_id,
                doc_id,
                chunk_text,
                chunk_metadata,
                sparse_embedding
            FROM document_chunks
            WHERE sparse_embedding IS NOT NULL {where_clause}
            LIMIT :limit
        """)
        
        results = db.execute(query, {'limit': n_results * 3}).fetchall()
        
        # Compute similarity scores
        scored_results = []
        for row in results:
            # Compute cosine similarity
            sparse_embedding = row.sparse_embedding
            similarity = self._compute_sparse_similarity(query_sparse_dict, sparse_embedding)
            
            scored_results.append({
                'id': row.chunk_id,
                'doc_id': row.doc_id,
                'text': row.chunk_text,
                'metadata': row.chunk_metadata if row.chunk_metadata else {},
                'score': similarity
            })
        
        # Sort by score and return top n_results
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        return scored_results[:n_results]
    
    def _compute_sparse_similarity(
        self,
        query_dict: Dict[int, float],
        stored_dict: Dict
    ) -> float:
        """Compute cosine similarity between two sparse vectors."""
        # Convert stored dict keys to integers
        stored_dict_int = {int(k): v for k, v in stored_dict.items()}
        
        # Get common keys
        common_keys = set(query_dict.keys()) & set(stored_dict_int.keys())
        
        if not common_keys:
            return 0.0
        
        # Compute dot product
        dot_product = sum(query_dict[k] * stored_dict_int[k] for k in common_keys)
        
        # Compute magnitudes
        query_magnitude = np.sqrt(sum(v**2 for v in query_dict.values()))
        stored_magnitude = np.sqrt(sum(v**2 for v in stored_dict_int.values()))
        
        if query_magnitude == 0 or stored_magnitude == 0:
            return 0.0
        
        # Cosine similarity
        return dot_product / (query_magnitude * stored_magnitude)
    
    def delete_document(self, doc_id: str) -> Tuple[int, int]:
        """
        Delete all chunks for a document.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            Tuple of (chunks_deleted, chunks_deleted) for compatibility
        """
        db = next(get_db())
        
        try:
            # Delete all chunks for the document
            deleted = db.query(DocumentChunk).filter_by(doc_id=doc_id).delete()
            db.commit()
            
            logger.info(f"Deleted {deleted} chunks for document {doc_id}")
            return deleted, deleted
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting document {doc_id}: {e}")
            return 0, 0
        finally:
            db.close()
    
    def get_document_chunk_count(self, doc_id: str) -> int:
        """Get the number of chunks for a document."""
        db = next(get_db())
        try:
            count = db.query(DocumentChunk).filter_by(doc_id=doc_id).count()
            return count
        except Exception as e:
            logger.error(f"Error getting chunk count: {e}")
            return 0
        finally:
            db.close()
    
    def get_all_document_ids(self) -> set:
        """Get all unique document IDs."""
        db = next(get_db())
        try:
            results = db.execute(text("SELECT DISTINCT doc_id FROM document_chunks"))
            return {str(row[0]) for row in results}
        except Exception as e:
            logger.error(f"Error getting document IDs: {e}")
            return set()
        finally:
            db.close()
    
    def healthcheck(self) -> bool:
        """Check if the vector store is healthy."""
        db = next(get_db())
        try:
            # Check pgvector
            result = db.execute(text("SELECT 1"))
            result.fetchone()
            
            # Check if table exists
            result = db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'document_chunks'
                )
            """))
            exists = result.fetchone()[0]
            
            return exists
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
        finally:
            db.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        db = next(get_db())
        try:
            # Get counts
            total_chunks = db.query(DocumentChunk).count()
            
            # Get unique document count
            result = db.execute(text("SELECT COUNT(DISTINCT doc_id) FROM document_chunks"))
            doc_count = result.fetchone()[0]
            
            # Check if indexes exist
            result = db.execute(text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'document_chunks' 
                AND indexname LIKE '%hnsw%'
            """))
            has_hnsw = len(result.fetchall()) > 0
            
            return {
                "healthy": True,
                "total_chunks": total_chunks,
                "document_count": doc_count,
                "has_hnsw_index": has_hnsw,
                "storage_type": "PostgreSQL with pgvector"
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    # Compatibility methods for backward compatibility
    def _get_client(self):
        """For backward compatibility - returns None."""
        return None, None, None


# Export for compatibility
__all__ = ['PGVectorStore']