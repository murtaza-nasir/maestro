"""
Central configuration for all file paths used in the Maestro application.
This ensures consistency across all components.
"""

from pathlib import Path

# Base paths
DATA_BASE_PATH = Path("/app/ai_researcher/data")

# Vector store - single source of truth
VECTOR_STORE_PATH = DATA_BASE_PATH / "vector_store"

# Document storage paths
RAW_FILES_PATH = DATA_BASE_PATH / "raw_pdfs"
MARKDOWN_PATH = DATA_BASE_PATH / "processed" / "markdown"
METADATA_PATH = DATA_BASE_PATH / "processed" / "metadata"
METADATA_DB_PATH = DATA_BASE_PATH / "processed" / "metadata.db"

# Legacy paths for backward compatibility (if needed)
LEGACY_DATA_PATH = Path("/app/data")
LEGACY_RAW_FILES_PATH = LEGACY_DATA_PATH / "raw_files"
LEGACY_MARKDOWN_PATH = LEGACY_DATA_PATH / "markdown_files"

# Ensure critical directories exist
def ensure_directories():
    """Create necessary directories if they don't exist."""
    for path in [VECTOR_STORE_PATH, RAW_FILES_PATH, MARKDOWN_PATH, METADATA_PATH]:
        path.mkdir(parents=True, exist_ok=True)