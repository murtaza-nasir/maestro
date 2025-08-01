import sqlite3
import json # Import the json module
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any # Added Dict, Any for metadata type hint
import datetime

class Database:
    """
    Handles interaction with an SQLite database to track processed documents
    and their associated metadata.
    """
    def __init__(self, db_path: str | Path = "data/processed/metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        self._create_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        """Creates the processed_documents table if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_documents (
                    doc_id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL UNIQUE,
                    processing_timestamp TEXT NOT NULL,
                    metadata_json TEXT  -- Store full extracted metadata as JSON string
                )
            """)
            conn.commit()
            print(f"Database table 'processed_documents' ensured at {self.db_path}")
        except sqlite3.Error as e:
            print(f"Error creating database table: {e}")
        finally:
            conn.close()

    def add_processed_document(self, doc_id: str, original_filename: str, metadata: dict):
        """
        Adds a record for a successfully processed document.

        Args:
            doc_id: The unique ID assigned during processing.
            original_filename: The original name of the PDF file.
            metadata: The dictionary of extracted metadata.
        """
        timestamp = datetime.datetime.now().isoformat()
        metadata_str = json.dumps(metadata) # Serialize metadata to JSON string

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO processed_documents (doc_id, original_filename, processing_timestamp, metadata_json)
                VALUES (?, ?, ?, ?)
            """, (doc_id, original_filename, timestamp, metadata_str))
            conn.commit()
            print(f"Added record for '{original_filename}' (ID: {doc_id}) to database.")
        except sqlite3.IntegrityError:
            # This can happen if the original_filename (UNIQUE constraint) already exists
            print(f"Warning: Document '{original_filename}' already exists in the database.")
        except sqlite3.Error as e:
            print(f"Error adding document record for '{original_filename}': {e}")
            conn.rollback() # Rollback changes on error
        finally:
            conn.close()

    def is_file_processed(self, original_filename: str) -> bool:
        """
        Checks if a document with the given original filename has already been processed.

        Args:
            original_filename: The original name of the PDF file.

        Returns:
            True if the file has been processed, False otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 1 FROM processed_documents WHERE original_filename = ?
            """, (original_filename,))
            result = cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            print(f"Error checking if file '{original_filename}' is processed: {e}")
            return False # Assume not processed if there's a DB error
        finally:
            conn.close()

    def get_metadata_by_doc_id(self, doc_id: str) -> Optional[dict]:
         """Retrieves the metadata for a given doc_id."""
         conn = self._get_connection()
         cursor = conn.cursor()
         try:
             cursor.execute("SELECT metadata_json FROM processed_documents WHERE doc_id = ?", (doc_id,))
             result = cursor.fetchone()
             if result and result[0]:
                 return json.loads(result[0]) # Deserialize JSON string
             else:
                 return None
         except sqlite3.Error as e:
             print(f"Error retrieving metadata for doc_id '{doc_id}': {e}")
             return None
         except json.JSONDecodeError as e:
              print(f"Error decoding metadata JSON for doc_id '{doc_id}': {e}")
              return None
         finally:
             conn.close()

    def get_document_info_by_filename(self, original_filename: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the doc_id and metadata_json for a given original_filename.

        Args:
            original_filename: The original name of the PDF file.

        Returns:
            A dictionary containing 'doc_id' and 'metadata_json' if found, otherwise None.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT doc_id, metadata_json FROM processed_documents WHERE original_filename = ?
            """, (original_filename,))
            result = cursor.fetchone()
            if result:
                return {"doc_id": result[0], "metadata_json": result[1]}
            else:
                return None
        except sqlite3.Error as e:
            print(f"Error retrieving document info for filename '{original_filename}': {e}")
            return None
        finally:
            conn.close()

    def get_all_documents(self, limit: Optional[int] = None, offset: Optional[int] = None) -> list[Dict[str, Any]]:
        """
        Retrieves all documents from the database with optional pagination.
        
        Args:
            limit: Maximum number of documents to return (None for all)
            offset: Number of documents to skip (for pagination)
            
        Returns:
            List of dictionaries containing document information and metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Build query with optional pagination
            query = """
                SELECT doc_id, original_filename, processing_timestamp, metadata_json 
                FROM processed_documents 
                ORDER BY processing_timestamp DESC
            """
            params = []
            
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                
            if offset is not None:
                query += " OFFSET ?"
                params.append(offset)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            documents = []
            for row in results:
                doc_id, original_filename, processing_timestamp, metadata_json = row
                
                # Parse metadata
                metadata = {}
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding metadata JSON for doc_id '{doc_id}': {e}")
                        metadata = {}
                
                # Create document record
                doc_record = {
                    'id': doc_id,
                    'original_filename': original_filename,
                    'processing_timestamp': processing_timestamp,
                    'metadata': metadata
                }
                documents.append(doc_record)
            
            return documents
            
        except sqlite3.Error as e:
            print(f"Error retrieving all documents: {e}")
            return []
        finally:
            conn.close()
    
    def get_document_count(self) -> int:
        """
        Returns the total number of documents in the database.
        
        Returns:
            Total count of documents
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM processed_documents")
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.Error as e:
            print(f"Error getting document count: {e}")
            return 0
        finally:
            conn.close()
    
    def search_documents(self, search_term: str, limit: Optional[int] = None, offset: Optional[int] = None) -> list[Dict[str, Any]]:
        """
        Search documents by title, authors, or filename.
        
        Args:
            search_term: Term to search for
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            
        Returns:
            List of matching documents
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Search in filename and metadata JSON (which contains title, authors, etc.)
            query = """
                SELECT doc_id, original_filename, processing_timestamp, metadata_json 
                FROM processed_documents 
                WHERE original_filename LIKE ? OR metadata_json LIKE ?
                ORDER BY processing_timestamp DESC
            """
            params = [f"%{search_term}%", f"%{search_term}%"]
            
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                
            if offset is not None:
                query += " OFFSET ?"
                params.append(offset)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            documents = []
            for row in results:
                doc_id, original_filename, processing_timestamp, metadata_json = row
                
                # Parse metadata
                metadata = {}
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding metadata JSON for doc_id '{doc_id}': {e}")
                        metadata = {}
                
                # Create document record
                doc_record = {
                    'id': doc_id,
                    'original_filename': original_filename,
                    'processing_timestamp': processing_timestamp,
                    'metadata': metadata
                }
                documents.append(doc_record)
            
            return documents
            
        except sqlite3.Error as e:
            print(f"Error searching documents: {e}")
            return []
        finally:
            conn.close()

    def get_filtered_documents(
        self, 
        search: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        sort_by: str = "processing_timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None, 
        offset: Optional[int] = None
    ) -> Tuple[list[Dict[str, Any]], int]:
        """
        Get filtered and paginated documents with total count.
        
        Args:
            search: Search term for title, authors, or filename
            author: Filter by author name
            year: Filter by publication year
            journal: Filter by journal/source
            sort_by: Field to sort by (processing_timestamp, original_filename)
            sort_order: Sort order (asc, desc)
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            
        Returns:
            Tuple of (documents list, total_count)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Build WHERE clause conditions
            where_conditions = []
            params = []
            
            if search:
                where_conditions.append("(original_filename LIKE ? OR metadata_json LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            
            if author:
                where_conditions.append("metadata_json LIKE ?")
                params.append(f"%{author}%")
            
            if year:
                where_conditions.append("metadata_json LIKE ?")
                params.append(f'%"publication_year": {year}%')
            
            if journal:
                where_conditions.append("metadata_json LIKE ?")
                params.append(f"%{journal}%")
            
            # Build WHERE clause
            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)
            
            # Validate sort_by and sort_order
            valid_sort_fields = ["processing_timestamp", "original_filename"]
            if sort_by not in valid_sort_fields:
                sort_by = "processing_timestamp"
            
            if sort_order.lower() not in ["asc", "desc"]:
                sort_order = "desc"
            
            # Get total count first
            count_query = f"SELECT COUNT(*) FROM processed_documents {where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Build main query
            query = f"""
                SELECT doc_id, original_filename, processing_timestamp, metadata_json 
                FROM processed_documents 
                {where_clause}
                ORDER BY {sort_by} {sort_order.upper()}
            """
            
            # Add pagination
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
                
            if offset is not None:
                query += " OFFSET ?"
                params.append(offset)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            documents = []
            for row in results:
                doc_id, original_filename, processing_timestamp, metadata_json = row
                
                # Parse metadata
                metadata = {}
                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding metadata JSON for doc_id '{doc_id}': {e}")
                        metadata = {}
                
                # Create document record
                doc_record = {
                    'id': doc_id,
                    'original_filename': original_filename,
                    'processing_timestamp': processing_timestamp,
                    'metadata': metadata
                }
                documents.append(doc_record)
            
            return documents, total_count
            
        except sqlite3.Error as e:
            print(f"Error getting filtered documents: {e}")
            return [], 0
        finally:
            conn.close()

    def update_document_status(self, doc_id: str, status: str):
        """
        Placeholder method to update a document's status (e.g., in case of errors).
        Could be expanded to add a 'status' column to the table.
        """
        # This is just a placeholder. A real implementation would likely involve
        # ALTER TABLE to add a status column and then UPDATE statements.
        print(f"Placeholder: Update status for doc_id {doc_id} to '{status}' (not implemented).")


# Example Usage (for testing purposes)
# Note: This block will be removed later to avoid syntax issues.
if __name__ == "__main__":
    import json # Need json for example usage

    # Use a temporary DB for testing
    temp_db_path = Path("data/temp_metadata.db")
    db = Database(db_path=temp_db_path)

    # Test adding a document
    test_meta = {"title": "Test Doc", "authors": ["Tester"], "publication_year": 2024}
    db.add_processed_document("test001", "test.pdf", test_meta)

    # Test checking if processed
    print(f"Is 'test.pdf' processed? {db.is_file_processed('test.pdf')}")
    print(f"Is 'other.pdf' processed? {db.is_file_processed('other.pdf')}")

    # Test adding duplicate
    db.add_processed_document("test002", "test.pdf", test_meta) # Should print warning

    # Test retrieving metadata
    retrieved_meta = db.get_metadata_by_doc_id("test001")
    print(f"Retrieved metadata for test001: {retrieved_meta}")

    # Clean up temp db file
    if temp_db_path.exists():
        os.remove(temp_db_path)
        print(f"Removed temporary database: {temp_db_path}")
