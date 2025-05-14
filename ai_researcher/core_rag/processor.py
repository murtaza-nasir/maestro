import os
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import shutil # Import shutil at the top

import torch
import pymupdf # PyMuPDF
import pymupdf4llm # For fallback or specific markdown conversion if needed later
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser

import sqlite3 # Needed for Database integration (error handling)
# json is imported above

# Import the new components
from .metadata_extractor import MetadataExtractor
from .chunker import Chunker
from .database import Database # Import the Database class
from .embedder import TextEmbedder # Import Embedder
from .vector_store import VectorStore # Import VectorStore

class DocumentProcessor:
    """
    Handles processing of PDF documents:
    1. Extracts initial text for metadata using pymupdf (header/footer method).
    2. Converts PDF to Markdown using marker.
    3. Assigns a unique document ID.
    4. Extracts structured metadata using an LLM.
    5. Chunks the Markdown content.
    """
    def __init__(
        self,
        pdf_dir: str | Path = "data/raw_pdfs",
        markdown_dir: str | Path = "data/processed/markdown",
        metadata_dir: str | Path = "data/processed/metadata",
        db_path: Optional[str | Path] = None,
        embedder: Optional[TextEmbedder] = None,
        vector_store: Optional[VectorStore] = None,
        force_reembed: bool = False, # Add force_reembed flag
        # marker_model_dir is handled by env var MARKER_MODEL_DIR
        device: Optional[str] = None
    ):
        self.pdf_dir = Path(pdf_dir)
        self.markdown_dir = Path(markdown_dir)
        self.metadata_dir = Path(metadata_dir)
        db_path = Path(db_path) if db_path else Path("data/processed/metadata.db") # Default path

        # Ensure directories exist
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True) # Ensure DB directory exists too

        # Force device to cuda:4 if available, otherwise fallback as before
        self.device = device or ("cuda:4" if torch.cuda.is_available() and torch.cuda.device_count() > 4 else ("cuda" if torch.cuda.is_available() else "cpu"))
        print(f"DocumentProcessor using device: {self.device}")

        # Initialize Marker components
        self.marker_models = create_model_dict(device=self.device)
        default_marker_options = {
            "output_format": "markdown",
            "device": self.device,
            "batch_multiplier": 2,
        }
        self.marker_config = ConfigParser(cli_options=default_marker_options)
        self.marker_converter = PdfConverter(
            config=self.marker_config.generate_config_dict(),
            artifact_dict=self.marker_models,
            processor_list=self.marker_config.get_processors(),
            renderer=self.marker_config.get_renderer()
        )

        # Initialize other components
        self.metadata_extractor = MetadataExtractor()
        self.chunker = Chunker()
        self.database = Database(db_path=db_path)
        self.embedder = embedder
        self.vector_store = vector_store
        self.force_reembed = force_reembed # Store the flag

        if self.embedder is None or self.vector_store is None:
            print("Warning: DocumentProcessor initialized without embedder or vector_store. Embedding/storing will be skipped.")
        if self.force_reembed:
            print("Warning: --force-reembed flag is active. All PDFs will be re-processed and re-embedded.")

    # --- Methods correctly indented within the class ---

    def _extract_header_footer_text(self, pdf_path: Path) -> str:
        """
        Extracts text from the first page, including header and footer,
        using the pymupdf logic from the example. Used for metadata extraction hint.
        """
        try:
            doc = pymupdf.open(pdf_path)
            if not doc or len(doc) == 0:
                print(f"Warning: Could not open or empty PDF: {pdf_path}")
                return ""

            first_page = doc[0]
            page_height = first_page.rect.height
            blocks = first_page.get_text("dict", flags=11)["blocks"]

            header_threshold = 0.1 * page_height
            header_blocks = [b for b in blocks if b["bbox"][3] <= header_threshold]
            header_blocks.sort(key=lambda b: b["bbox"][1])
            header_text_parts = [span["text"].strip() for block in header_blocks for line in block["lines"] for span in line["spans"] if span["text"].strip()]
            header_text = " ".join(header_text_parts)

            footer_threshold = 0.9 * page_height
            footer_blocks = [b for b in blocks if b["bbox"][1] >= footer_threshold]
            footer_blocks.sort(key=lambda b: b["bbox"][1])
            footer_text_parts = [span["text"].strip() for block in footer_blocks for line in block["lines"] for span in line["spans"] if span["text"].strip()]
            footer_text = " ".join(footer_text_parts)

            main_text = first_page.get_text("text")
            doc.close()

            combined_text = f"## Extracted Header:\n{header_text}\n\n## Extracted Footer:\n{footer_text}\n\n## First Page Content:\n{main_text}"
            return combined_text

        except Exception as e:
            print(f"Error extracting header/footer text from {pdf_path}: {e}")
            return ""

    def process_pdf(self, pdf_path: Path) -> Optional[Dict]:
        """
        Processes a single PDF file.
        Returns a dictionary containing doc_id, markdown content, metadata, and chunks.
        Returns None if processing fails or file is already processed.
        """
        if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
            print(f"Error: Invalid PDF path: {pdf_path}")
            return None

        start_time = time.time()
        print(f"Processing PDF: {pdf_path.name}...")

        existing_doc_info = self.database.get_document_info_by_filename(pdf_path.name)
        doc_id = None
        final_metadata = None

        # Check if already processed and decide whether to skip or force
        if existing_doc_info and not self.force_reembed:
            print(f"Skipping '{pdf_path.name}': Already processed and found in database (use --force-reembed to override).")
            return None
        elif existing_doc_info and self.force_reembed:
            print(f"Force re-embedding '{pdf_path.name}': Found existing record in database.")
            doc_id = existing_doc_info['doc_id']
            # Attempt to load existing metadata, otherwise use basic
            try:
                final_metadata = json.loads(existing_doc_info['metadata_json']) if existing_doc_info['metadata_json'] else {}
                final_metadata['doc_id'] = doc_id # Ensure doc_id is present
                final_metadata['original_filename'] = pdf_path.name # Ensure filename is present/updated
                print(f"  Using existing doc_id: {doc_id} and loaded metadata.")
            except json.JSONDecodeError:
                print(f"  Warning: Could not parse existing metadata for {doc_id}. Using basic metadata.")
                final_metadata = {"doc_id": doc_id, "original_filename": pdf_path.name}
        else:
            # File not in DB or force_reembed is true and file wasn't in DB anyway
            print(f"Processing '{pdf_path.name}' as a new document.")
            # Generate unique ID
            doc_id = str(uuid.uuid4())[:8]
            final_metadata = {"doc_id": doc_id, "original_filename": pdf_path.name}

        # --- Metadata Extraction (only if not loaded from DB or if forced and failed to load) ---
        # We might want to avoid re-running LLM metadata extraction if force_reembed is just for syncing vector store.
        # Let's refine: only extract if metadata wasn't successfully loaded above.
        if final_metadata is None or not final_metadata.get('title'): # Check if metadata is basic or missing key fields
            print("  Extracting metadata using LLM...")
            initial_text_for_metadata = self._extract_header_footer_text(pdf_path)
            extracted_metadata = self.metadata_extractor.extract(initial_text_for_metadata)
            if extracted_metadata:
                # Ensure doc_id and filename are preserved if they existed
                base_meta = {"doc_id": doc_id, "original_filename": pdf_path.name}
                extracted_metadata.update(base_meta) # Overwrite doc_id/filename from extraction if needed
                final_metadata = extracted_metadata
                print(f"  Successfully extracted metadata for {pdf_path.name}.")
                # Save metadata JSON (overwrite if exists)
                metadata_filename = f"{doc_id}.json"
                metadata_save_path = self.metadata_dir / metadata_filename
                try:
                    with open(metadata_save_path, "w", encoding="utf-8") as f:
                        json.dump(final_metadata, f, indent=2, ensure_ascii=False)
                    print(f"  Saved metadata to: {metadata_save_path}")
                except IOError as e:
                    print(f"  Error saving metadata file {metadata_save_path}: {e}")
            else:
                print(f"  Warning: Metadata extraction failed for {pdf_path.name}. Using basic metadata.")
                # Ensure final_metadata is at least the base if extraction fails
                if final_metadata is None:
                     final_metadata = {"doc_id": doc_id, "original_filename": pdf_path.name}

        # --- Add or Update record in DB ---
        # Use add_processed_document which handles potential updates based on filename
        self.database.add_processed_document(doc_id, pdf_path.name, final_metadata)
        # The metadata extraction logic was already handled correctly in the previous block.
        # --- Get Markdown Content (Convert or Load Existing) ---
        md_filename = f"{doc_id}.md"
        md_save_path = self.markdown_dir / md_filename
        markdown_content = None

        if md_save_path.exists() and self.force_reembed:
            # If forcing re-embed and markdown exists, try loading it
            print(f"  Found existing Markdown file: {md_save_path}. Loading content.")
            try:
                with open(md_save_path, "r", encoding="utf-8") as f:
                    markdown_content = f.read()
                if not markdown_content:
                     print(f"  Warning: Existing Markdown file {md_save_path} is empty. Will attempt Marker conversion.")
                     # Fall through to Marker conversion
            except IOError as e:
                print(f"  Error reading existing Markdown file {md_save_path}: {e}. Will attempt Marker conversion.")
                # Fall through to Marker conversion
            except Exception as e:
                 print(f"  Unexpected error reading existing Markdown file {md_save_path}: {e}. Will attempt Marker conversion.")
                 # Fall through to Marker conversion

        if markdown_content is None:
            # If not loaded (doesn't exist, force_reembed is false, or loading failed), run Marker
            print(f"  Converting PDF to Markdown using Marker...")
            try:
                marker_result = self.marker_converter(str(pdf_path))
                markdown_content = marker_result.markdown
                if not markdown_content:
                    print(f"Warning: Marker produced empty markdown for {pdf_path.name}. Skipping document.")
                    # Update status? Maybe not, as it might be a valid empty doc. Let chunking handle it.
                    # Let's return None here to be safe, as empty content can't be embedded.
                    self.database.update_document_status(doc_id, "error_marker_empty_output")
                    return None
            except Exception as e:
                print(f"  Error converting PDF with Marker for {pdf_path.name}: {e}")
                self.database.update_document_status(doc_id, "error_marker_conversion")
                return None # Fail if marker fails

            # Save the newly generated Markdown
            try:
                with open(md_save_path, "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                print(f"  Saved Markdown to: {md_save_path}")
            except IOError as e:
                print(f"  Error saving Markdown file {md_save_path}: {e}")
                self.database.update_document_status(doc_id, "error_saving_markdown")
                return None # Fail if cannot save markdown

        # --- Chunk the Markdown ---
        print(f"  Chunking Markdown content...")
        # Ensure the metadata passed to the chunker *definitely* has the correct filename
        if final_metadata:
             final_metadata['original_filename'] = pdf_path.name
        else:
             # Should not happen at this stage, but handle defensively
             print(f"  Warning: final_metadata is None before chunking for {pdf_path.name}. Using basic.")
             final_metadata = {"doc_id": doc_id, "original_filename": pdf_path.name}

        chunks = self.chunker.chunk(markdown_content, doc_metadata=final_metadata)
        print(f"  Generated {len(chunks)} chunks for {pdf_path.name}.")

        # --- Embed and Store Chunks ---
        chunks_added_count = 0
        if self.embedder and self.vector_store and chunks:
            try:
                print(f"  Embedding {len(chunks)} chunks for {pdf_path.name}...")
                chunks_with_embeddings = self.embedder.embed_chunks(chunks)
                print(f"  Embedding complete. Adding to vector store...")
                self.vector_store.add_chunks(chunks_with_embeddings)
                chunks_added_count = len(chunks)
                print(f"  Successfully added {chunks_added_count} chunks to vector store for {pdf_path.name}.")
            except Exception as e_embed_store:
                print(f"Error embedding/storing chunks for {pdf_path.name}: {e_embed_store}")
                # Decide if this should be a fatal error for the document or just a warning
                # For now, log the error and continue, but don't return the document data
                # as it wasn't fully processed into the vector store.
                # Alternatively, could return partial data or raise exception.
                # Let's return None to indicate failure at this stage.
                self.database.update_document_status(doc_id, "error_embedding_storing")
                return None
        elif not chunks:
             print(f"  Skipping embedding/storing for {pdf_path.name}: No chunks generated.")
        else:
             print(f"  Skipping embedding/storing for {pdf_path.name}: Embedder or VectorStore not provided.")
        # --- End Embed and Store ---


        end_time = time.time()
        print(f"Finished processing {pdf_path.name} in {end_time - start_time:.2f} seconds (Added {chunks_added_count} chunks to vector store).")

        # Return minimal data now, as chunks are handled internally
        return {
            "doc_id": doc_id,
            "original_filename": pdf_path.name,
            "chunks_generated": len(chunks), # Keep track of generated chunks
            "chunks_added_to_vector_store": chunks_added_count, # Keep track of added chunks
            "extracted_metadata": final_metadata # Return metadata for potential logging/summary
            # Removed markdown_path and markdown_content as they are less relevant for the summary return
        }

    def process_directory(self) -> Tuple[int, int]:
        """
        Processes all PDF files in the configured pdf_dir.
        Embeds and stores chunks for each document immediately after processing.
        Returns a tuple: (total_documents_processed, total_chunks_added).
        """
        total_docs_attempted = 0
        total_docs_successfully_processed = 0 # Docs that completed without error
        total_chunks_added = 0
        pdf_files = list(self.pdf_dir.glob("*.pdf"))
        total_docs_attempted = len(pdf_files)
        print(f"Found {total_docs_attempted} PDF(s) in {self.pdf_dir}")

        if not pdf_files:
            print("No PDF files found to process.")
            return 0, 0

        for pdf_path in pdf_files:
            result = self.process_pdf(pdf_path) # process_pdf handles embedding/storing and skipping/forcing logic
            if result:
                # result is not None, meaning processing (including embedding/storing) was successful for this doc
                total_docs_successfully_processed += 1
                total_chunks_added += result.get("chunks_added_to_vector_store", 0)
            # If result is None, an error occurred or it was skipped (and not forced)

        print(f"\nFinished processing directory.")
        print(f"Attempted to process: {total_docs_attempted} PDF(s).")
        print(f"Successfully processed/re-processed: {total_docs_successfully_processed} PDF(s).")
        print(f"Total chunks added/updated in vector store during this run: {total_chunks_added}.")
        # Return the count of successfully processed docs and chunks added in this run
        return total_docs_successfully_processed, total_chunks_added
