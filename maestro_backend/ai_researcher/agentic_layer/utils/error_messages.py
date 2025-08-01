"""
Centralized error message utilities for user-friendly API configuration and error handling.
"""

def get_api_configuration_error_message() -> str:
    """Returns a user-friendly message for API configuration errors."""
    return """### **API Configuration Required**

Your request cannot be processed because the AI model API key is not configured. Please follow the steps below to connect to an AI provider.

## How to Configure Your API Key

1.  Click the **Settings** icon, located in the bottom-left corner of the application.
2.  In the Settings window, navigate to the **AI Config** tab.
3.  Choose one of the provider options below, enter your credentials, and save.
---
## Provider Options

### OpenRouter (Recommended)
OpenRouter offers access to a wide range of models (like GPT-4, Claude, and Gemini) through a single API key, making it a flexible and straightforward option.

* **To set up:** Select **OpenRouter** as the AI Provider and paste your API key.
* **Get your key:** [openrouter.ai](https://openrouter.ai/keys)

### OpenAI
This option provides direct access to OpenAI's proprietary models.

* **To set up:** Select **OpenAI API** as the AI Provider and paste your API key.
* **Get your key:** [platform.openai.com](https://platform.openai.com/api-keys)

### Custom Provider
This advanced option is for connecting to a self-hosted model or any third-party service that uses an OpenAI-compatible API endpoint.

* **To set up:** Select **Custom Provider**, enter the **Base URL** of your endpoint, and provide the corresponding API key if required.
---
## Final Step

After entering your details, click **Save & Close**. You can then try your request again."""


def get_api_quota_error_message() -> str:
    """Returns a user-friendly message for API quota/billing errors."""
    return """💳 **API Credits Exhausted**

Your AI model API credits have been exhausted or your account has billing issues.

**🔧 To Fix This:**
1. Check your API provider's billing dashboard:
   - **OpenRouter**: Visit [openrouter.ai/activity](https://openrouter.ai/activity)
   - **OpenAI**: Visit [platform.openai.com/usage](https://platform.openai.com/usage)

2. Add credits to your account or update your billing information

3. If you're using a free tier, you may have hit usage limits

**💡 Alternative:**
- Switch to a different AI provider in Settings > AI Config
- OpenRouter often has lower costs and better availability

Once you've resolved the billing issue, I'll be ready to help you again!"""


def get_api_error_message(status_code: int) -> str:
    """Returns a user-friendly message for general API errors."""
    return f"I'm experiencing technical difficulties (API Error {status_code}). Please try again in a moment, or check your API configuration in Settings if the problem persists."


def get_generic_error_message() -> str:
    """Returns a user-friendly message for unexpected errors."""
    return "I'm experiencing technical difficulties. Please try again in a moment."


def handle_api_error(error) -> str:
    """
    Centralized error handling that returns appropriate user-friendly messages.
    
    Args:
        error: The exception object (typically openai.AuthenticationError, openai.APIStatusError, etc.)
        
    Returns:
        User-friendly error message string
    """
    import openai
    
    if isinstance(error, openai.AuthenticationError):
        return get_api_configuration_error_message()
    elif isinstance(error, openai.APIStatusError):
        if error.status_code == 401:
            return get_api_configuration_error_message()
        elif error.status_code == 403:
            return get_api_quota_error_message()
        else:
            return get_api_error_message(error.status_code)
    else:
        return get_generic_error_message()
