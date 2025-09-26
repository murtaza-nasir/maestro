"""
Utility functions for sanitizing text data before saving to PostgreSQL JSONB fields.
PostgreSQL JSONB doesn't support null bytes (\u0000) in text strings.
"""
import re
from typing import Any, Dict, List, Union
import json


def sanitize_text(text: str) -> str:
    """
    Remove null characters and other problematic Unicode characters from text.
    
    Args:
        text: Input text that may contain null characters
        
    Returns:
        Sanitized text safe for PostgreSQL JSONB storage
    """
    if not isinstance(text, str):
        return text
    
    # Remove null characters (\u0000)
    text = text.replace('\x00', '')
    
    # Remove other control characters that might cause issues (0x00-0x1F except \t, \n, \r)
    # Keep tab (0x09), newline (0x0A), and carriage return (0x0D)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    return text


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively sanitize all string values in a dictionary.
    
    Args:
        data: Dictionary that may contain strings with null characters
        
    Returns:
        Sanitized dictionary safe for PostgreSQL JSONB storage
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_text(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = sanitize_list(value)
        else:
            sanitized[key] = value
    
    return sanitized


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    Recursively sanitize all string values in a list.
    
    Args:
        data: List that may contain strings with null characters
        
    Returns:
        Sanitized list safe for PostgreSQL JSONB storage
    """
    if not isinstance(data, list):
        return data
    
    sanitized = []
    for item in data:
        if isinstance(item, str):
            sanitized.append(sanitize_text(item))
        elif isinstance(item, dict):
            sanitized.append(sanitize_dict(item))
        elif isinstance(item, list):
            sanitized.append(sanitize_list(item))
        else:
            sanitized.append(item)
    
    return sanitized


def sanitize_for_jsonb(data: Union[str, Dict, List, Any]) -> Union[str, Dict, List, Any]:
    """
    Sanitize any data structure for safe storage in PostgreSQL JSONB.
    
    Args:
        data: Data to be stored in JSONB field
        
    Returns:
        Sanitized data safe for PostgreSQL JSONB storage
    """
    if isinstance(data, str):
        return sanitize_text(data)
    elif isinstance(data, dict):
        return sanitize_dict(data)
    elif isinstance(data, list):
        return sanitize_list(data)
    else:
        # For other types, try to convert to string and sanitize if needed
        try:
            if hasattr(data, '__dict__'):
                # Handle Pydantic models and other objects with __dict__
                return sanitize_dict(data.__dict__)
            elif hasattr(data, 'model_dump'):
                # Handle Pydantic v2 models
                return sanitize_dict(data.model_dump())
        except:
            pass
        return data


def sanitize_json_string(json_str: str) -> str:
    """
    Sanitize a JSON string by parsing it, cleaning the data, and re-serializing.
    
    Args:
        json_str: JSON string that may contain null characters
        
    Returns:
        Sanitized JSON string safe for PostgreSQL JSONB storage
    """
    try:
        data = json.loads(json_str)
        sanitized_data = sanitize_for_jsonb(data)
        return json.dumps(sanitized_data, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, just sanitize as plain text
        return sanitize_text(json_str)