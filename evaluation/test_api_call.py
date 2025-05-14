import json
import os
import asyncio
import logging
import random
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("api_test_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api_test")

# Set up OpenRouter client with OpenAI compatibility in async mode
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    timeout=60.0  # Increase timeout to 60 seconds
)

async def test_api_call(model="anthropic/claude-3.7-sonnet"):
    """Test a single API call to debug response format issues."""
    logger.info(f"Testing API call to model: {model}")
    
    # Use a simple test prompt
    test_prompt = """You are a fact-checking expert. Please verify if the following statement is true:
    
    "The sky is blue during a clear day."
    
    Provide your answer strictly in the following JSON format:
    {
      "verification_result": "yes | no | partial"
    }"""
    
    try:
        # Make the API call
        logger.info("Sending API request...")
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": test_prompt}],
            temperature=0.0,
            max_tokens=512,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "verification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "verification_result": {
                                "type": "string",
                                "enum": ["yes", "no", "partial"],
                                "description": "Whether the statement is true"
                            }
                        },
                        "required": ["verification_result"],
                        "additionalProperties": False
                    }
                }
            }
        )
        
        # Print the full response object for debugging
        logger.info(f"Response status: {response.model_dump().get('object', 'unknown')}")
        logger.info(f"Response ID: {response.id if hasattr(response, 'id') else 'unknown'}")
        
        # Extract and print the content
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content.strip()
            logger.info(f"Response content: {repr(content)}")
            
            # Try to parse the JSON
            try:
                result = json.loads(content)
                logger.info(f"Parsed JSON: {result}")
                return True
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                return False
        else:
            logger.error(f"No choices in response or unexpected response format: {response}")
            return False
            
    except Exception as e:
        logger.error(f"API call error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def test_with_retries(model, max_retries=3):
    """Test API call with retries."""
    for attempt in range(1, max_retries + 1):
        logger.info(f"Attempt {attempt}/{max_retries}")
        success = await test_api_call(model)
        if success:
            logger.info(f"Successful API call on attempt {attempt}")
            return
        else:
            if attempt < max_retries:
                delay = 2 ** attempt  # Exponential backoff
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
    
    logger.error(f"Failed after {max_retries} attempts")

async def main():
    """Main function to test API calls to different models."""
    import sys
    
    if len(sys.argv) > 1:
        model = sys.argv[1]
    else:
        model = "anthropic/claude-3.7-sonnet"
    
    logger.info(f"Testing model: {model}")
    await test_with_retries(model)

if __name__ == "__main__":
    asyncio.run(main())
