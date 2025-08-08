"""
Utilities for handling JSON responses from LLMs.

This module provides functions for parsing, sanitizing, and preparing JSON data
returned by LLMs for use with Pydantic models. It handles common issues like
string representations of JSON objects inside JSON arrays, and provides
specialized functions for common use cases.
"""

import json
import ast
import re
import logging
from typing import Any, Dict, List, Tuple, Type, TypeVar, Optional, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')

def parse_json_string_recursively(data: Any) -> Any:
    """
    Recursively parse any string that looks like a JSON object into an actual object.
    This helps handle cases where LLMs return JSON strings inside JSON.
    
    Args:
        data: The data to parse, which could be a dict, list, string, or other type.
        
    Returns:
        The parsed data with any JSON strings converted to Python objects.
    """
    if isinstance(data, dict):
        # Process each key-value pair in the dictionary
        return {k: parse_json_string_recursively(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Process each item in the list
        return [parse_json_string_recursively(item) for item in data]
    elif isinstance(data, tuple):
        # Handle tuples by converting each item and returning as a list
        # This is important for cases where json.loads or ast.literal_eval returns a tuple
        return [parse_json_string_recursively(item) for item in data]
    elif isinstance(data, str):
        # Try to parse the string as JSON if it looks like a JSON object or array
        data = data.strip()
        if (data.startswith('{') and data.endswith('}')) or (data.startswith('[') and data.endswith(']')):
            try:
                # Try standard JSON parsing first
                return json.loads(data)
            except json.JSONDecodeError:
                try:
                    # If that fails, try using ast.literal_eval which can handle some non-standard JSON
                    return ast.literal_eval(data)
                except (SyntaxError, ValueError):
                    try:
                        # Last resort: replace single quotes with double quotes and try again
                        fixed_str = data.replace("'", '"')
                        return json.loads(fixed_str)
                    except json.JSONDecodeError:
                        # Special case: Check if this is a string containing multiple JSON objects
                        # This happens in the problematic JSON example where multiple objects are concatenated
                        if data.count('}, {') > 0:
                            try:
                                # Try to parse it as a list of objects by wrapping it in square brackets
                                wrapped_data = '[' + data + ']'
                                return json.loads(wrapped_data)
                            except json.JSONDecodeError:
                                # If that fails, return the original string
                                return data
                        # If all parsing attempts fail, return the original string
                        return data
        return data
    else:
        # For other types (int, float, bool, None), return as is
        return data

def extract_json_from_thinking_model_response(raw_response: str) -> str:
    """
    Extract JSON from responses that may contain thinking tokens or reasoning text.
    
    Thinking models (like GPT-5, o1-preview, o1-mini) often include reasoning
    text before the actual JSON response. This function attempts to extract
    the JSON portion from such responses.
    
    Args:
        raw_response: The raw response from a thinking model that may contain
                     thinking tokens followed by JSON.
                     
    Returns:
        The extracted JSON string, or the original response if no JSON is found.
    """
    if not raw_response or not raw_response.strip():
        return raw_response
    
    content = raw_response.strip()
    
    # Look for JSON objects or arrays
    # Try to find the first occurrence of { or [ that starts a valid JSON structure
    json_start_chars = ['{', '[']
    
    for start_char in json_start_chars:
        start_idx = content.find(start_char)
        if start_idx == -1:
            continue
            
        # Try to find a complete JSON structure starting from this position
        for end_idx in range(len(content), start_idx, -1):
            potential_json = content[start_idx:end_idx]
            try:
                # Test if this is valid JSON
                json.loads(potential_json)
                return potential_json
            except json.JSONDecodeError:
                continue
    
    # If we couldn't find valid JSON, try looking for common JSON patterns
    # Look for content between triple backticks (even if not marked as json)
    
    # Pattern to match content in code blocks
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)```'
    code_blocks = re.findall(code_block_pattern, content, re.MULTILINE)
    
    for block in code_blocks:
        block_content = block.strip()
        if block_content.startswith(('{', '[')):
            try:
                json.loads(block_content)
                return block_content
            except json.JSONDecodeError:
                continue
    
    # Last resort: try to find JSON-like patterns in the text
    # Look for lines that start with { or [ and attempt to parse from there
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith(('{', '[')):
            # Try to build JSON from this line onwards
            remaining_content = '\n'.join(lines[i:])
            for start_char in json_start_chars:
                if line.startswith(start_char):
                    try:
                        json.loads(remaining_content)
                        return remaining_content
                    except json.JSONDecodeError:
                        # Try just this line
                        try:
                            json.loads(line)
                            return line
                        except json.JSONDecodeError:
                            continue
    
    # If all else fails, return the original content
    return content

def sanitize_json_string(raw_json: str) -> str:
    """
    Sanitize a JSON string by removing code blocks, extra whitespace, etc.
    
    Args:
        raw_json: The raw JSON string to sanitize.
        
    Returns:
        A cleaned JSON string ready for parsing.
    """
    # First, try to extract JSON from thinking model responses
    content_with_json_extracted = extract_json_from_thinking_model_response(raw_json)
    
    sanitized_content = content_with_json_extracted.strip()
    if sanitized_content.startswith("```json"):
        sanitized_content = sanitized_content[len("```json"):].strip()
    if sanitized_content.startswith("```"):
        sanitized_content = sanitized_content[len("```"):].strip()
    if sanitized_content.endswith("```"):
        sanitized_content = sanitized_content[:-len("```")].strip()
    return sanitized_content

def parse_llm_json_response(raw_json: str) -> Dict[str, Any]:
    """
    Parse a JSON response from an LLM, handling common issues.
    
    Args:
        raw_json: The raw JSON string from the LLM.
        
    Returns:
        A dictionary representing the parsed JSON.
        
    Raises:
        json.JSONDecodeError: If the JSON cannot be parsed after all attempts.
    """
    sanitized_json = sanitize_json_string(raw_json)
    
    try:
        parsed_data = json.loads(sanitized_json)
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON parsing failed: {e}. Attempting to fix common issues...")
        try:
            # Try to fix common issues like single quotes instead of double quotes
            fixed_json = sanitized_json.replace("'", '"')
            parsed_data = json.loads(fixed_json)
            logger.info("JSON parsing succeeded after replacing single quotes with double quotes.")
        except json.JSONDecodeError:
            # If that fails, try using ast.literal_eval
            try:
                parsed_data = ast.literal_eval(sanitized_json)
                logger.info("JSON parsing succeeded using ast.literal_eval.")
            except (SyntaxError, ValueError) as e:
                logger.error(f"All JSON parsing attempts failed: {e}")
                raise json.JSONDecodeError(f"Failed to parse JSON after multiple attempts: {e}", sanitized_json, 0)
    
    # Apply recursive parsing to handle nested JSON strings
    return parse_json_string_recursively(parsed_data)

def flatten_nested_json_strings(data: Any) -> Any:
    """
    Recursively parse nested JSON strings in the data.
    This is an alias for parse_json_string_recursively for clarity in certain contexts.
    
    Args:
        data: The data to process.
        
    Returns:
        The processed data with nested JSON strings parsed.
    """
    return parse_json_string_recursively(data)

def handle_tuple_in_list(data: List[Any]) -> List[Any]:
    """
    Handle the case where a list contains tuples of items.
    This is a common issue with LLM responses where the model returns a tuple
    inside a list instead of multiple separate items.
    
    Args:
        data: A list that might contain tuples.
        
    Returns:
        A flattened list where tuples are expanded into separate items.
    """
    if not data:
        return data
    
    # Special case: if the list has only one item and it's a tuple,
    # and that tuple contains dictionaries, we should flatten it
    if len(data) == 1 and isinstance(data[0], tuple):
        return list(data[0])
    
    flattened_items = []
    for item in data:
        if isinstance(item, tuple):
            # Add each item in the tuple as a separate item
            flattened_items.extend(list(item))
        else:
            # If it's not a tuple, add it as is
            flattened_items.append(item)
    
    return flattened_items

def filter_null_values_from_list(data: List[Any]) -> List[Any]:
    """
    Filter out None/null values from a list.
    
    This is useful for handling cases where the LLM includes null values in a list
    that should only contain valid objects, which would cause Pydantic validation errors.
    
    Args:
        data: The list that might contain null values.
        
    Returns:
        A filtered list with null values removed.
    """
    if not data:
        return data
    
    return [item for item in data if item is not None]

def convert_string_to_subsection_topic(title_str: str) -> Dict[str, Any]:
    """
    Convert a string to a SuggestedSubsectionTopic dictionary.
    
    This is useful when the LLM returns a simple string instead of a properly
    formatted SuggestedSubsectionTopic object. The function creates a valid
    SuggestedSubsectionTopic with default values for the required fields.
    
    Args:
        title_str: The string to convert to a SuggestedSubsectionTopic.
        
    Returns:
        A dictionary representing a SuggestedSubsectionTopic with the string as the title.
    """
    return {
        "title": title_str,
        "description": f"Topics related to {title_str}",
        "relevant_note_ids": [],
        "reasoning": f"This topic was identified as a potential subsection based on the analyzed notes."
    }

def prepare_for_pydantic_validation(data: Dict[str, Any], model_class: Type[T]) -> Dict[str, Any]:
    """
    Prepare data for validation with a Pydantic model.
    
    This function handles common issues that arise when validating LLM responses
    with Pydantic models, such as:
    - Nested JSON strings that need to be parsed
    - Tuples that need to be converted to lists
    - Special handling for specific field types
    - Filtering out null values from lists
    - Converting strings to proper objects for certain fields
    
    Args:
        data: The data to prepare.
        model_class: The Pydantic model class to prepare for.
        
    Returns:
        The prepared data ready for validation.
    """
    # First, recursively parse any JSON strings
    parsed_data = parse_json_string_recursively(data)
    
    # Handle specific fields that might need special treatment
    for field_name, field_info in model_class.__annotations__.items():
        if field_name in parsed_data:
            # Handle lists that might contain tuples or null values
            if isinstance(parsed_data[field_name], list) and len(parsed_data[field_name]) > 0:
                # Filter out null values from the list
                parsed_data[field_name] = filter_null_values_from_list(parsed_data[field_name])
                if not parsed_data[field_name]:  # If list is now empty after filtering
                    parsed_data[field_name] = []
                    logger.info(f"Filtered out null values from list for field '{field_name}', resulting in empty list")
                    continue
                
                # Check if the first item is a tuple
                if isinstance(parsed_data[field_name][0], tuple):
                    parsed_data[field_name] = handle_tuple_in_list(parsed_data[field_name])
                    logger.info(f"Flattened tuples in list for field '{field_name}'")
                
                # Special handling for suggested_subsection_topics field
                if field_name == "suggested_subsection_topics":
                    # Check if any items are strings and convert them to proper objects
                    for i, item in enumerate(parsed_data[field_name]):
                        if isinstance(item, str):
                            parsed_data[field_name][i] = convert_string_to_subsection_topic(item)
                            logger.info(f"Converted string to SuggestedSubsectionTopic for item at index {i}: {item}")
                
                # Handle the case where items in the list are strings that look like JSON
                for i, item in enumerate(parsed_data[field_name]):
                    if isinstance(item, str):
                        if (item.startswith('{') and item.endswith('}')) or (item.startswith('[') and item.endswith(']')):
                            try:
                                parsed_item = json.loads(item)
                                parsed_data[field_name][i] = parsed_item
                                logger.info(f"Parsed JSON string in list for field '{field_name}' at index {i}")
                            except json.JSONDecodeError:
                                # If parsing fails, keep the original string
                                pass
    
    # Apply a second pass of recursive parsing to handle any nested JSON strings
    # that might have been created during the first pass
    parsed_data = parse_json_string_recursively(parsed_data)
    
    return parsed_data

def extract_non_schema_fields(data: Dict[str, Any], model_class: Type[T]) -> Dict[str, Any]:
    """
    Extract fields from the data that are not part of the Pydantic model schema.
    
    This is useful for handling fields like 'scratchpad_update' that might be
    included in the LLM response but are not part of the formal schema.
    
    Args:
        data: The data to extract fields from.
        model_class: The Pydantic model class to check against.
        
    Returns:
        A dictionary containing fields that are not part of the model schema.
    """
    schema_fields = set(model_class.__annotations__.keys())
    extra_fields = {k: v for k, v in data.items() if k not in schema_fields}
    return extra_fields
