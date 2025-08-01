import logging
import asyncio # <-- Import asyncio
import aiofiles # <-- Import aiofiles
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Awaitable # Added Callable, Awaitable
from pydantic import BaseModel, Field

# Use absolute imports if needed, assuming config/base paths might be relevant
# from ai_researcher import config # Example if config holds allowed paths

logger = logging.getLogger(__name__)

# Define the input schema for the tool
class FileReaderInput(BaseModel):
    filepath: str = Field(..., description="The absolute path to the file to read.")
    # Optional: Add allowed base paths for security
    allowed_base_path: str = Field("ai_researcher/data/processed/markdown", description="The base directory within which file reading is permitted.")

class FileReaderTool:
    """
    A tool for agents to read the full text content of a specified file,
    primarily intended for accessing markdown files containing document content.
    Includes basic path validation for security.
    """
    def __init__(self):
        self.name = "read_full_document"
        self.description = (
            "Reads the full text content of a specified markdown file. "
            "Use this when a retrieved snippet is insufficient and full document context is needed. "
            "Requires the absolute path to the file, typically reconstructed from metadata."
        )
        self.parameters_schema = FileReaderInput
        logger.info("FileReaderTool initialized.")

    # Keep _is_path_allowed synchronous as it's fast path validation
    def _is_path_allowed(self, filepath_str: str, allowed_base_path_str: str) -> bool:
        """
        Checks if the requested filepath (potentially a symlink) is located
        within the allowed base directory structure. Does NOT resolve the final target.
        """
        # Skip path check if allowed_base_path_str is None or 'None'
        if allowed_base_path_str is None or allowed_base_path_str == 'None':
            logger.info(f"Skipping path check because allowed_base_path is None or 'None'")
            return True
            
        try:
            # Resolve the allowed base path relative to CWD if it's relative
            allowed_base_path_obj = Path(allowed_base_path_str)
            if allowed_base_path_obj.is_absolute():
                allowed_base_path = allowed_base_path_obj.resolve()
            else:
                # Assume relative paths for allowed_base_path are relative to CWD
                allowed_base_path = Path.cwd().joinpath(allowed_base_path_str).resolve()
                logger.debug(f"Relative allowed_base_path resolved to: {allowed_base_path}")

            # Get the absolute path of the *link itself* (or the file if not a link)
            # Important: Use resolve(strict=False) initially in case the link target is broken,
            # but we still need to check the link's location.
            # However, for the is_relative_to check, we need a path that exists.
            # Let's resolve the *parent* directory of the filepath first.
            filepath_obj = Path(filepath_str)
            
            # Check if the file exists at the given path
            if not filepath_obj.exists():
                # If the file doesn't exist at the given path, try to find it in the data directory
                # This handles the case where the path is constructed incorrectly in Docker
                from ai_researcher.config import is_running_in_docker
                
                # Get the doc_id from the filepath (assuming it's the filename without extension)
                doc_id = filepath_obj.stem
                
                # Try alternative paths
                alternative_paths = []
                
                # In Docker, try the container path
                if is_running_in_docker():
                    alternative_paths.append(Path("/app/ai_researcher/data/processed/markdown") / f"{doc_id}.md")
                
                # Try relative to current working directory
                alternative_paths.append(Path.cwd() / "ai_researcher/data/processed/markdown" / f"{doc_id}.md")
                
                # Try one level up (for cases where cwd is inside ai_researcher)
                alternative_paths.append(Path.cwd().parent / "ai_researcher/data/processed/markdown" / f"{doc_id}.md")
                
                for alt_path in alternative_paths:
                    if alt_path.exists():
                        logger.info(f"Original path '{filepath_str}' not found, using alternative path: {alt_path}")
                        filepath_obj = alt_path
                        break
                else:
                    logger.error(f"File not found at original path '{filepath_str}' or any alternative paths")
                    return False
            
            link_location_path = filepath_obj.parent.resolve() # Resolve the directory containing the link/file

            # Check if the directory containing the link/file is within the allowed base
            # If the file was found at an alternative path, we'll skip this check
            # since we've already verified it exists in a valid location
            if filepath_str == str(filepath_obj) and not link_location_path.is_relative_to(allowed_base_path):
                logger.warning(f"Directory '{link_location_path}' containing the file/link '{filepath_obj.name}' is outside allowed base '{allowed_base_path}'.")
                return False

            # If the link/file exists and its directory is allowed, permit access
            logger.debug(f"Path check passed: '{filepath_obj}' is valid.")
            return True

        except Exception as e:
            logger.error(f"Error during path validation for '{filepath_str}' against '{allowed_base_path_str}': {e}")
            return False

    async def execute(
        self,
        filepath: str,
        allowed_base_path: str,
        log_queue: Optional[asyncio.Queue] = None, # <-- Add log_queue parameter
        original_filename: Optional[str] = None,
        feedback_callback: Optional[Callable[..., None]] = None # Use more generic Callable for simplicity
    ) -> str:
        """
        Reads the content of a file specified by filepath, ensuring it's within the allowed_base_path.
        Executes the file reading process asynchronously, handling @symlinks correctly.
        Optionally sends feedback upon successful read, including the original filename if provided.

        Args:
            filepath: The absolute or relative path to the file (potentially a symlink).
            allowed_base_path: The base directory allowed for reading the file/symlink itself.

        Returns:
            The full text content of the file as a string, or an error message string.
        """
        logger.info(f"Executing FileReaderTool for path: '{filepath}'")

        # --- Security Check (Checks location of the link/file itself) ---
        if not self._is_path_allowed(filepath, allowed_base_path):
            # Error logged within _is_path_allowed
            # Construct error message based on potentially resolved paths for clarity
            try:
                 resolved_filepath = Path(filepath).resolve()
                 # Skip creating Path object if allowed_base_path is None or 'None'
                 if allowed_base_path is None or allowed_base_path == 'None':
                     error_msg = f"Access denied: Path '{filepath}' cannot be validated (allowed_base_path is None)."
                 else:
                     resolved_allowed = Path(allowed_base_path).resolve()
                     error_msg = f"Access denied: Resolved path '{resolved_filepath}' is outside the allowed directory '{resolved_allowed}'."
            except Exception: # Handle potential resolution errors
                 error_msg = f"Access denied: Path '{filepath}' is outside the allowed directory '{allowed_base_path}' (or resolution failed)."
            logger.error(error_msg)
            return f"Error: {error_msg}"

        # --- Async File Reading Logic ---
        try:
            file_path_obj = Path(filepath)
            if file_path_obj.suffix.lower() == ".md":
                # Read markdown file
                async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
                    full_text = await f.read()
                logger.info(f"Successfully read {len(full_text)} characters from markdown: {filepath}")

                # --- Send Feedback ---
                if feedback_callback:
                    try:
                        markdown_filename = file_path_obj.name # Get just the markdown filename
                        feedback_payload = {
                            "type": "file_read",
                            "filename": markdown_filename, # Markdown filename (e.g., doc_id.md)
                            "original_filename": original_filename # Original filename (e.g., paper.pdf)
                        }
                        # Wrap the payload before calling the callback
                        formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                        # Call with log_queue and formatted_message
                        if log_queue and feedback_callback:
                            feedback_callback(log_queue, formatted_message)
                            logger.debug(f"Sent 'file_read' feedback via callback for: {markdown_filename} (Original: {original_filename})")
                        elif feedback_callback:
                             logger.warning(f"Feedback callback provided for file read '{filepath}', but log_queue is None. Cannot send feedback.")
                    except Exception as fb_e:
                        # Log the specific error during callback invocation
                        logger.error(f"Error invoking feedback callback for file read '{filepath}': {fb_e}", exc_info=True)
                # --- End Feedback ---

                return full_text
            else:
                error_msg = f"Unsupported file type: {file_path_obj.suffix}. Only .md is currently supported."
                logger.error(error_msg)
                return f"Error: {error_msg}"

        except FileNotFoundError:
            error_msg = f"File not found: {filepath}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        except IOError as e:
            error_msg = f"I/O error reading file {filepath}: {e}"
            logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"
        except Exception as e:
            # Catch any other unexpected issues
            error_msg = f"Error processing file {filepath}: {e}"
            logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"
