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
