"""
Utility functions for API endpoints.
"""
import json
import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def _make_serializable(data: Any) -> Any:
    """Recursively converts non-JSON-serializable types in dicts/lists to strings."""
    if isinstance(data, dict):
        if hasattr(data, 'model_dump'):
            try:
                serializable_dict = data.model_dump(mode='json')
                return _make_serializable(serializable_dict)
            except Exception:
                return repr(data)
        else:
            return {k: _make_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_make_serializable(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    elif isinstance(data, (datetime.datetime, datetime.date)):
         return data.isoformat()
    elif isinstance(data, Path):
        return str(data)
    else:
        try:
            json.dumps(data)
            return data
        except (TypeError, OverflowError):
             return repr(data)

def clean_tool_call_arguments(tool_calls: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    Clean tool call arguments by removing technical/internal parameters before sending to frontend.
    
    Args:
        tool_calls: List of tool call dictionaries with arguments
        
    Returns:
        Cleaned list of tool calls with technical arguments removed
    """
    if not tool_calls:
        return tool_calls
    
    # Arguments to remove from tool calls (technical/internal parameters)
    technical_args_to_remove = {
        'filepath',
        'allowed_base_path', 
        'feedback_callback',
        'log_queue',
        'update_callback',
        'tool_registry_override'
    }
    
    cleaned_tool_calls = []
    
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            cleaned_tool_calls.append(tool_call)
            continue
            
        cleaned_call = tool_call.copy()
        
        # Clean arguments if present
        if 'arguments' in cleaned_call and isinstance(cleaned_call['arguments'], dict):
            cleaned_args = {}
            for key, value in cleaned_call['arguments'].items():
                if key not in technical_args_to_remove:
                    cleaned_args[key] = value
                    
            # For read_full_document tool, add the original_filename if available
            if (tool_call.get('tool_name') == 'read_full_document' and 
                'original_filename' in tool_call.get('arguments', {})):
                cleaned_args['original_filename'] = tool_call['arguments']['original_filename']
                    
            cleaned_call['arguments'] = cleaned_args
            
        cleaned_tool_calls.append(cleaned_call)
    
    return cleaned_tool_calls

async def replace_document_codes_in_tool_calls(tool_calls: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    Replace document codes with actual filenames in tool call arguments.
    
    Args:
        tool_calls: List of tool call dictionaries
        
    Returns:
        Tool calls with document codes replaced by actual filenames
    """
    if not tool_calls:
        return tool_calls
    
    try:
        from services.document_service import document_service
        
        processed_tool_calls = []
        
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                processed_tool_calls.append(tool_call)
                continue
                
            processed_call = tool_call.copy()
            
            # Process arguments if present
            if 'arguments' in processed_call and isinstance(processed_call['arguments'], dict):
                processed_args = {}
                for key, value in processed_call['arguments'].items():
                    if isinstance(value, str):
                        # Replace document codes in string values
                        processed_value = await document_service.replace_document_codes_in_text(value)
                        processed_args[key] = processed_value
                    else:
                        processed_args[key] = value
                        
                processed_call['arguments'] = processed_args
                
            # Process result_summary if present
            if 'result_summary' in processed_call and isinstance(processed_call['result_summary'], str):
                processed_call['result_summary'] = await document_service.replace_document_codes_in_text(
                    processed_call['result_summary']
                )
                
            # Process error if present
            if 'error' in processed_call and isinstance(processed_call['error'], str):
                processed_call['error'] = await document_service.replace_document_codes_in_text(
                    processed_call['error']
                )
                
            processed_tool_calls.append(processed_call)
            
        return processed_tool_calls
        
    except Exception as e:
        logger.warning(f"Failed to replace document codes in tool calls: {e}")
        return tool_calls

def clean_execution_log_entry_for_frontend(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean an execution log entry for frontend consumption by removing technical arguments
    and replacing document codes with actual filenames.
    
    Args:
        log_entry: Dictionary representing an execution log entry
        
    Returns:
        Cleaned log entry suitable for frontend
    """
    cleaned_entry = log_entry.copy()
    
    # Clean tool calls if present
    if 'tool_calls' in cleaned_entry:
        cleaned_entry['tool_calls'] = clean_tool_call_arguments(cleaned_entry['tool_calls'])
        
    return cleaned_entry

def clean_input_summary_for_display(input_summary: str) -> str:
    """
    Clean input summary to make it more user-friendly by extracting key information
    from tool call arguments instead of showing raw JSON.
    
    Args:
        input_summary: Raw input summary string
        
    Returns:
        Cleaned, user-friendly summary
    """
    if not input_summary:
        return input_summary
    
    # Handle document_search tool calls
    if "document_search" in input_summary and "Args:" in input_summary:
        try:
            # Extract query from the args
            import re
            query_match = re.search(r"'query':\s*'([^']+)'", input_summary)
            if query_match:
                query = query_match.group(1)
                return f"Search documents for: \"{query}\""
        except Exception:
            pass
    
    # Handle web_search tool calls
    if "web_search" in input_summary and "Args:" in input_summary:
        try:
            # Extract query from the args
            import re
            query_match = re.search(r"'query':\s*'([^']+)'", input_summary)
            if query_match:
                query = query_match.group(1)
                return f"Search web for: \"{query}\""
        except Exception:
            pass
    
    # Handle read_full_document tool calls
    if "read_full_document" in input_summary and "Args:" in input_summary:
        try:
            # Extract document_id from the args
            import re
            doc_id_match = re.search(r"'document_id':\s*'([^']+)'", input_summary)
            if doc_id_match:
                doc_id = doc_id_match.group(1)
                return f"Read document: {doc_id}"
        except Exception:
            pass
    
    # For other tool calls, try to extract the tool name and make it more readable
    if "Execute Tool:" in input_summary and "Args:" in input_summary:
        try:
            import re
            tool_match = re.search(r"Execute Tool:\s*(\w+)", input_summary)
            if tool_match:
                tool_name = tool_match.group(1)
                # Make tool name more readable
                readable_name = tool_name.replace('_', ' ').title()
                return f"Execute {readable_name}"
        except Exception:
            pass
    
    return input_summary

async def process_execution_log_entry_for_frontend(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process an execution log entry for frontend consumption by cleaning technical arguments
    and replacing document codes with actual filenames.
    
    Args:
        log_entry: Dictionary representing an execution log entry
        
    Returns:
        Processed log entry suitable for frontend
    """
    # First clean technical arguments
    cleaned_entry = clean_execution_log_entry_for_frontend(log_entry)
    
    # Clean input_summary to make it more user-friendly
    if 'input_summary' in cleaned_entry and isinstance(cleaned_entry['input_summary'], str):
        cleaned_entry['input_summary'] = clean_input_summary_for_display(cleaned_entry['input_summary'])
    
    # Then replace document codes with filenames
    try:
        from services.document_service import document_service
        
        # Replace document codes in action text
        if 'action' in cleaned_entry and isinstance(cleaned_entry['action'], str):
            cleaned_entry['action'] = await document_service.replace_document_codes_in_text(
                cleaned_entry['action']
            )
            
        # Replace document codes in input_summary
        if 'input_summary' in cleaned_entry and isinstance(cleaned_entry['input_summary'], str):
            cleaned_entry['input_summary'] = await document_service.replace_document_codes_in_text(
                cleaned_entry['input_summary']
            )
            
        # Replace document codes in output_summary  
        if 'output_summary' in cleaned_entry and isinstance(cleaned_entry['output_summary'], str):
            cleaned_entry['output_summary'] = await document_service.replace_document_codes_in_text(
                cleaned_entry['output_summary']
            )
            
        # Replace document codes in tool calls
        if 'tool_calls' in cleaned_entry:
            cleaned_entry['tool_calls'] = await replace_document_codes_in_tool_calls(
                cleaned_entry['tool_calls']
            )
            
    except Exception as e:
        logger.warning(f"Failed to replace document codes in log entry: {e}")
        
    return cleaned_entry
