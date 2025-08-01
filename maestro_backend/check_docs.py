#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

from database.database import get_db
from database.models import Document
from sqlalchemy.orm import Session

def main():
    # Get database session
    db_gen = get_db()
    db: Session = next(db_gen)

    try:
        # Check the processing status of documents in the group
        doc_ids = ['1311a207', 'c7066e54', 'd73607d8', '99c885e5']
        
        print('=== Document Processing Status ===')
        for doc_id in doc_ids:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                print(f'Document {doc_id}:')
                print(f'  Filename: {doc.original_filename}')
                print(f'  Processing Status: {doc.processing_status}')
                print(f'  Upload Progress: {doc.upload_progress}')
                print(f'  Processing Error: {doc.processing_error}')
                print(f'  File Size: {doc.file_size}')
                print(f'  File Path: {doc.file_path}')
                print()
            else:
                print(f'Document {doc_id}: NOT FOUND')
                print()
    finally:
        db.close()

if __name__ == "__main__":
    main()
