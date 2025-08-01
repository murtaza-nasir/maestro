import re
from typing import List, Dict, Any, Optional

class Chunker:
    """
    Splits Markdown text into overlapping chunks based on paragraphs.
    """
    def __init__(
        self,
        paragraphs_per_chunk: int = 2,
        overlap_paragraphs: int = 1 # How many paragraphs to overlap
    ):
        if overlap_paragraphs >= paragraphs_per_chunk:
            raise ValueError("Overlap paragraphs must be less than paragraphs per chunk.")
        self.paragraphs_per_chunk = paragraphs_per_chunk
        self.overlap_paragraphs = overlap_paragraphs
        # Use regex to split by one or more newlines, keeping separators
        # This helps handle various spacing styles in markdown
        self._paragraph_split_pattern = re.compile(r'(\n\s*\n+)')

    def chunk(self, markdown_content: str, doc_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Chunks the provided Markdown content.

        Args:
            markdown_content: The full Markdown text of the document.
            doc_metadata: Optional dictionary containing document-level metadata
                          (e.g., doc_id) to be added to each chunk's metadata.

        Returns:
            A list of chunk dictionaries, where each dictionary contains
            the chunk 'text' and its 'metadata'.
        """
        if not markdown_content:
            return []

        # Split into paragraphs, keeping the newline separators for potential reconstruction
        parts = self._paragraph_split_pattern.split(markdown_content)
        # Filter out empty strings and combine text parts with their subsequent separator
        paragraphs = []
        current_paragraph = ""
        for part in parts:
            if part: # Ignore empty strings resulting from split
                if self._paragraph_split_pattern.match(part):
                    # If it's a separator, append it to the current paragraph and start a new one
                    if current_paragraph: # Avoid adding separator if paragraph is empty
                         current_paragraph += part
                         paragraphs.append(current_paragraph.strip())
                    current_paragraph = "" # Reset for next paragraph
                else:
                    # If it's text, append it to the current paragraph
                    current_paragraph += part
        # Add the last paragraph if it wasn't followed by a separator
        if current_paragraph.strip():
            paragraphs.append(current_paragraph.strip())

        if not paragraphs:
            return [] # No paragraphs found

        chunks = []
        doc_id = doc_metadata.get("doc_id", "unknown_doc") if doc_metadata else "unknown_doc"
        chunk_id_counter = 0

        # Iterate through paragraphs with a step size determined by the non-overlapping part
        step = self.paragraphs_per_chunk - self.overlap_paragraphs
        for i in range(0, len(paragraphs), step):
            # Define the end index for the current chunk
            end_index = i + self.paragraphs_per_chunk
            # Get the paragraphs for the current chunk
            current_paragraphs = paragraphs[i:end_index]

            if not current_paragraphs:
                continue # Skip if somehow we get an empty slice

            # Join the paragraphs back together with double newlines
            chunk_text = "\n\n".join(current_paragraphs)

            # Create chunk metadata
            chunk_meta = {
                "doc_id": doc_id,
                "chunk_id": chunk_id_counter,
                # Add other relevant metadata if needed, e.g., start/end paragraph index
                "start_paragraph_index": i,
                "end_paragraph_index": min(end_index, len(paragraphs)) -1 # Inclusive index
            }
            # Merge document metadata (excluding doc_id again)
            if doc_metadata:
                chunk_meta.update({k: v for k, v in doc_metadata.items() if k != "doc_id"})

            chunks.append({
                "text": chunk_text,
                "metadata": chunk_meta
            })
            chunk_id_counter += 1

            # Break if the last chunk processed includes the final paragraph
            if end_index >= len(paragraphs):
                 break


        return chunks
