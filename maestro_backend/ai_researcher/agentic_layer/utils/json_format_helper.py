"""
JSON Format Helper with Automatic Fallback

This module provides utilities to handle JSON response formats with automatic
fallback from json_schema to json_object format when needed.
"""

from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel
import json
import logging

logger = logging.getLogger(__name__)

def get_json_schema_format(
    pydantic_model: type[BaseModel],
    schema_name: str = "response"
) -> Dict[str, Any]:
    """
    Get json_schema format configuration (OpenAI structured outputs).
    
    Args:
        pydantic_model: The Pydantic model class defining the schema
        schema_name: A descriptive name for the schema
        
    Returns:
        Dictionary with json_schema format configuration
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": pydantic_model.model_json_schema(),
            "strict": True  # Enable strict validation
        }
    }

def get_json_object_format() -> Dict[str, Any]:
    """
    Get json_object format configuration (basic JSON mode).
    
    Returns:
        Dictionary with json_object format configuration
    """
    return {"type": "json_object"}

def get_schema_instructions(pydantic_model: type[BaseModel]) -> str:
    """
    Generate clear schema instructions for models using json_object format.
    
    Args:
        pydantic_model: The Pydantic model class defining the schema
        
    Returns:
        String containing formatted schema instructions
    """
    schema = pydantic_model.model_json_schema()
    
    # Create a simplified, human-readable version of the schema
    instructions = "\n\nIMPORTANT: You must respond with a JSON object that EXACTLY follows this schema:\n"
    instructions += json.dumps(schema, indent=2)
    instructions += "\n\nAll required fields must be included. Use empty arrays [] for list fields with no items, and null for optional fields."
    
    return instructions

def enhance_messages_for_json_object(
    messages: List[Dict[str, str]],
    pydantic_model: type[BaseModel]
) -> List[Dict[str, str]]:
    """
    Enhance messages with schema instructions for json_object format.
    
    Args:
        messages: List of message dictionaries
        pydantic_model: The Pydantic model class defining the schema
        
    Returns:
        Enhanced messages list
    """
    # Make a copy to avoid modifying the original
    enhanced_messages = [msg.copy() for msg in messages]
    
    # Add schema instructions to the user message
    if enhanced_messages and enhanced_messages[-1]["role"] == "user":
        schema_instructions = get_schema_instructions(pydantic_model)
        enhanced_messages[-1]["content"] += schema_instructions
    
    # Enhance system prompt for better JSON compliance
    for i, msg in enumerate(enhanced_messages):
        if msg["role"] == "system":
            enhanced_messages[i]["content"] += "\n\nYou are a JSON-only assistant. Always respond with valid JSON matching the exact schema provided."
            break
    
    return enhanced_messages

def get_response_formats_with_fallback(
    pydantic_model: type[BaseModel],
    schema_name: str = "response"
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Get both json_schema and json_object formats for fallback strategy.
    
    Args:
        pydantic_model: The Pydantic model class defining the schema
        schema_name: A descriptive name for the schema
        
    Returns:
        Tuple of (json_schema_format, json_object_format)
    """
    json_schema_format = get_json_schema_format(pydantic_model, schema_name)
    json_object_format = get_json_object_format()
    
    return json_schema_format, json_object_format

def should_retry_with_json_object(error: Exception) -> bool:
    """
    Determine if an error indicates we should retry with json_object format.
    
    Args:
        error: The exception that occurred
        
    Returns:
        True if we should retry with json_object format
    """
    error_str = str(error).lower()
    
    # Check for known error patterns that indicate json_schema isn't supported
    json_schema_error_patterns = [
        "json_schema",
        "text.format",
        "response_format",
        "not supported",
        "invalid parameter",
        "unsupported format"
    ]
    
    for pattern in json_schema_error_patterns:
        if pattern in error_str:
            logger.info(f"Detected json_schema compatibility issue: {error_str[:200]}...")
            return True
    
    return False