import os
import json
from typing import Dict, Optional, Any
import openai
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Define the metadata schema based on the example
# (Could also be loaded from a separate JSON/YAML file)
METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "The full title of the paper/document"},
        "authors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of author names"
        },
        "journal_or_source": {"type": ["string", "null"], "description": "Full name of the journal, conference, or source website/organization"},
        "publication_year": {"type": ["integer", "null"], "description": "Publication year"},
        "abstract": {"type": ["string", "null"], "description": "The abstract or a brief summary of the document"},
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of relevant keywords or topics"
        }
    },
    "required": ["title", "authors"] # Make title and authors minimally required
}

# Example metadata for the schema prompt
METADATA_EXAMPLE = {
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"],
    "journal_or_source": "arXiv",
    "publication_year": 2017,
    "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
    "keywords": ["attention mechanism", "transformer", "sequence transduction", "natural language processing"]
}

class MetadataExtractor:
    """
    Extracts structured metadata from document text using an LLM.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1/",
        model: str = "openai/gpt-4o-mini", # Or another suitable model
        max_text_sample: int = 4000 # Characters to send to LLM
    ):
        load_dotenv() # Load .env file if present
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url
        self.model = model
        self.max_text_sample = max_text_sample

        if not self.api_key:
            logger.warning("API key not found in environment variables or passed directly.")
            self.client = None
        else:
            try:
                self.client = openai.OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key
                )
            except Exception as e:
                logger.error(f"Error initializing OpenAI client: {e}")
                self.client = None

    @classmethod
    def from_user_settings(cls, user_settings: Dict[str, Any], max_text_sample: int = 4000) -> 'MetadataExtractor':
        """
        Create a MetadataExtractor instance from user settings.
        
        Args:
            user_settings: User settings dictionary containing AI provider configuration
            max_text_sample: Maximum characters to send to LLM
            
        Returns:
            MetadataExtractor instance configured with user's AI provider settings
        """
        # Get AI endpoints settings from user settings
        ai_endpoints = user_settings.get('ai_endpoints', {})
        
        # Use the fast model configuration for metadata extraction (fast and efficient)
        fast_model_config = ai_endpoints.get('advanced_models', {}).get('fast', {})
        
        # Extract configuration from the fast model
        api_key = fast_model_config.get('api_key')
        base_url = fast_model_config.get('base_url')
        model = fast_model_config.get('model_name', 'openai/gpt-4o-mini')
        
        # If base_url is None/empty, get it from the provider this model uses
        if not base_url:
            provider_name = fast_model_config.get('provider', 'openrouter')
            providers = ai_endpoints.get('providers', {})
            provider_config = providers.get(provider_name, {})
            base_url = provider_config.get('base_url', 'https://openrouter.ai/api/v1/')
        
        # If no fast model configuration found, fallback to environment variables
        if not api_key or not model:
            logger.warning("No fast model configuration found in user settings, falling back to environment variables")
            api_key = None  # Will be loaded from environment in __init__
            base_url = "https://openrouter.ai/api/v1/"
            model = "openai/gpt-4o-mini"
        else:
            logger.info(f"Using user's fast model for metadata extraction: {model} at {base_url}")
        
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_text_sample=max_text_sample
        )

    def extract(self, text_sample: str) -> Optional[Dict[str, Any]]:
        """
        Extracts metadata from the provided text sample using the configured LLM.

        Args:
            text_sample: The text snippet (ideally from the start of the document)
                         to extract metadata from.

        Returns:
            A dictionary containing the extracted metadata, or None if extraction fails.
        """
        if not self.client:
            print("MetadataExtractor: LLM client not initialized. Cannot extract metadata.")
            return None
        if not text_sample:
            print("MetadataExtractor: No text sample provided.")
            return None

        # Limit the text sample size
        text_sample_truncated = text_sample[:self.max_text_sample]

        # Construct the prompt
        system_prompt = "You are a meticulous metadata extraction assistant. You always return valid JSON conforming exactly to the provided schema. Extract information based *only* on the provided text."
        user_prompt = f"""Extract metadata from the following document text snippet. Follow the JSON schema precisely. Use `null` for fields you cannot confidently determine from the text.

JSON Schema:
```json
{json.dumps(METADATA_SCHEMA, indent=2)}
```

Example Output Format:
```json
{json.dumps(METADATA_EXAMPLE, indent=2)}
```

Document Text Snippet:
---
{text_sample_truncated}
---

Extract the metadata based *only* on the text provided above and return it as JSON matching the schema.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"MetadataExtractor: Sending request to {self.model}...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000, # Adjust as needed
                temperature=0.1, # Low temperature for factual extraction
                response_format={
                    "type": "json_object", # Use json_object type for general JSON
                    # Note: OpenAI API might support json_schema directly,
                    # but json_object is more broadly compatible with OpenRouter models
                    # If using OpenAI directly, you might use:
                    # "type": "json_schema",
                    # "json_schema": {
                    #     "name": "document_metadata",
                    #     "schema": METADATA_SCHEMA
                    # }
                }
            )

            response_content = response.choices[0].message.content
            print("MetadataExtractor: Received response from LLM.")
            # print(f"Raw LLM Response:\n{response_content}") # Uncomment for debugging

            if not response_content:
                 print("MetadataExtractor: LLM returned empty content.")
                 return None

            # Parse the JSON response
            metadata = json.loads(response_content)
            print("MetadataExtractor: Successfully parsed JSON response.")

            # Basic validation (more robust validation using Pydantic could be added)
            if not isinstance(metadata, dict):
                 print(f"MetadataExtractor: LLM response is not a JSON object: {type(metadata)}")
                 return None
            if "title" not in metadata or not metadata["title"]:
                 print("MetadataExtractor: Error - Extracted metadata missing required 'title'.")
                 return None # Fail if required 'title' is missing

            # --- ADDED VALIDATION ---
            # Check for the 'authors' field as it's also required by the schema
            if "authors" not in metadata or not metadata["authors"] or not isinstance(metadata["authors"], list) or len(metadata["authors"]) == 0:
                 print("MetadataExtractor: Error - Extracted metadata missing required 'authors' or 'authors' is empty/invalid.")
                 # Optionally return partial metadata if title exists but authors are missing
                 # return {"title": metadata.get("title"), "warning": "Missing authors"}
                 return None # Fail if required 'authors' are missing or invalid

            # Optional: Check for publication_year if you want to be even stricter,
            # but it's not required by the current schema definition.
            # if "publication_year" not in metadata or metadata["publication_year"] is None:
            #     print("MetadataExtractor: Warning - Extracted metadata missing 'publication_year'.")

            return metadata

        except json.JSONDecodeError as e:
            print(f"MetadataExtractor: Error decoding JSON response from LLM: {e}")
            print(f"Raw response content was:\n{response_content}")
            return None
        except openai.APIError as e:
             print(f"MetadataExtractor: OpenAI API error: {e}")
             return None
        except Exception as e:
            print(f"MetadataExtractor: An unexpected error occurred: {e}")
            return None
