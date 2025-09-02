# AI Provider Configuration

Configure language model providers to power MAESTRO's research and writing capabilities.

![AI Configuration Interface](../../assets/images/settings/ai-config.png)

## Overview

MAESTRO supports multiple AI providers and allows flexible configuration:

- **Advanced Mode**: Configure separate providers and credentials for each model type
- **Custom Provider**: Connect to any OpenAI-compatible API endpoint
- **Local LLMs**: Connect to self-hosted models via custom endpoints

## Supported Providers

### Custom Provider (Recommended)

Connect to any OpenAI-compatible API endpoint. This is the most flexible option.

**Configuration:**

- **Provider**: Select "Custom Provider" from dropdown
- **API Key**: Enter your API key (or leave blank for local models)
- **Base URL**: Your endpoint URL

**Common Endpoints:**

- **OpenRouter**: `https://openrouter.ai/api/v1/`
- **OpenAI**: `https://api.openai.com/v1/`
- **Local Ollama**: `http://host.docker.internal:11434/v1/` or check your ollama config
- **Local vLLM**: `http://host.docker.internal:8000/v1/` or check your vllm config

### OpenRouter

Access to 100+ models through a unified API.

**Setup:**

1. Select "Openrouter" as the AI Provider
2. API Key: Get from [OpenRouter Dashboard](https://openrouter.ai/keys)
3. Base URL: `https://openrouter.ai/api/v1/`
4. Click "Test" to verify and load models

**Available Models:**

- Claude models (Anthropic)
- GPT models (OpenAI)
- Llama models (Meta)
- Mistral models
- Many more open and commercial models

**Pricing**: Pay-per-token, varies by model. Check [OpenRouter Pricing](https://openrouter.ai/models)

### OpenAI

Direct access to OpenAI's GPT models.

**Setup:**

1. Select "OpenAI" as the AI Provider
2. API Key: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
3. Base URL: `https://api.openai.com/v1/`
4. Click "Test" to verify and load models

**Available Models:**

- gpt-5-chat
- gpt-5-mini
- gpt-5-nano
- gpt-4o
- gpt-4o-mini

**Pricing**: Check [OpenAI Pricing](https://openai.com/api/pricing)

## Configuration Mode

### Advanced Configuration

MAESTRO uses Advanced Mode to configure separate providers and credentials for each model type:

1. Check "Advanced Configuration" checkbox
2. For each model type (Fast, Mid, Intelligent, Verifier):
      - Select "Custom Provider" from dropdown
      - Enter API key (if required)
      - Enter base URL for your provider
      - Click "Test" to load available models
      - Select model from dropdown
3. Click "Save & Close" to apply settings

**Example Setup:**

- **Fast Model**: 

      - Provider: Custom Provider
      - Base URL: `https://openrouter.ai/api/v1/`
      - Model: `meta-llama/llama-3.2-3b-instruct`

- **Mid Model**: 

      - Provider: Custom Provider
      - Base URL: `https://openrouter.ai/api/v1/`
      - Model: `anthropic/claude-3.5-haiku`

- **Intelligent Model**: 

      - Provider: Custom Provider
      - Base URL: `https://api.openai.com/v1/`
      - Model: `gpt-5-chat-latest`

- **Verifier Model**: 

      - Provider: Custom Provider
      - Base URL: `http://host.docker.internal:11434/v1/`
      - Model: `llama3.2` (local)

## Model Types and Agent Usage

MAESTRO uses four model categories, automatically assigned to different agents and tasks:

### Fast Model

**Agents using Fast Model:**

- **Planning Agent** - Creates research plans and outlines
- **Note Assignment Agent** - Distributes information to sections  
- **Query Strategy Agent** - Determines search strategies
- **Router Agent** - Routes tasks to appropriate agents

**Use Cases**: Quick decisions, simple formatting, routing logic

**Recommended Models**: Smaller, faster models (GPT-4o-mini, Claude Haiku, GPT-5-nano)

### Mid Model (Default)

**Agents using Mid Model:**

- **Research Agent** - Main research and information gathering
- **Writing Agent** - Document composition
- **Simplified Writing Agent** - Streamlined writing tasks
- **Messenger Agent** - User interaction and messaging
- **Default fallback** - Any undefined agent modes

**Use Cases**: General research, standard writing, analysis, user interaction

**Recommended Models**: Balanced models (GPT-5-mini, Claude-4-Sonnet, Qwen-2.5-72b-instruct)

### Intelligent Model

**Agents using Intelligent Model:**

- **Reflection Agent** - Critical analysis and feedback
- **Query Preparation Agent** - Complex query reformulation
- **Research Agent (critical tasks)** - When explicitly needed for complex analysis

**Use Cases**: Deep analysis, complex reasoning, quality assessment

**Recommended Models**: Most capable models (GPT-5-chat, Claude-4.1-Opus, Qwen3-235b-a22b-2507)

### Verifier Model

**Agents using Verifier Model:**

- **Verification tasks** - Fact-checking and validation
- **Quality control** - Ensuring accuracy of information

**Use Cases**: Fact verification, consistency checking

**Recommended Models**: Accurate, reliable models (typically same as Intelligent)

## Local LLM Setup

### Using Ollama

1. Install and run Ollama:
   ```bash
   # Install Ollama
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Pull a model
   ollama pull llama2
   
   # Run Ollama server
   ollama serve
   ```

2. Configure in MAESTRO:
      - Provider: Custom Provider
      - API Key: (use dummy unless you configured authentication)
      - Base URL: `http://host.docker.internal:11434/v1/`
      - Click "Test" to load available models
      - Model: Select from dropdown (e.g., "llama3.2", "mistral")

### Using LM Studio

1. Start LM Studio server on port 1234
2. Configure in MAESTRO:
      - Provider: Custom Provider
      - API Key: (use dummy unless you configured authentication)
      - Base URL: `http://host.docker.internal:1234/v1/`
      - Click "Test" to verify connection

### Using vLLM

1. Start vLLM server:
   ```bash
      python -m vllm.entrypoints.openai.api_server \
         --model "/home/user/models/Qwen_Qwen3-32B-AWQ" \
         --tensor-parallel-size 2 \
         --port 5000 \
         --host 0.0.0.0 \
         --gpu-memory-utilization 0.90 \
         --served-model-name "localmodel" \
         --disable-log-requests \
         --disable-custom-all-reduce \
         --enable-prefix-caching \
         --guided-decoding-backend "xgrammar" \
         --chat-template /home/user/vllm/qwen3_nonthinking.jinja
   ```

2. Configure in MAESTRO:
      - Provider: Custom Provider
      - API Key: (use dummy unless you configured authentication)
      - Base URL: `http://192.168.xxx.xxx:5000/v1/`
      - Click "Test" to load available model (will show as localmodel)

## Testing Your Configuration

### Connection Test

1. Enter your API credentials (API Key and Base URL)
2. Click the "Test" button next to the API Key field
3. Wait for verification (this fetches available models)
4. Success will populate the model dropdowns

### Model Selection

After successful connection test:

1. **Fast Model**: Select from dropdown for rapid, simple tasks
2. **Mid Model**: Select for balanced performance tasks  
3. **Intelligent Model**: Select for complex analysis (defaults to same as Mid if not set)
4. **Verifier Model**: Select for fact-checking (defaults to same as Mid if not set)

### Saving Configuration

1. After selecting all models, click "Save & Close"
2. Settings are saved per user
3. Changes take effect immediately for new research sessions

### Troubleshooting Connection Issues

**"Connection failed" error:**

- Verify API key is correct and active
- Check internet connection
- Ensure billing is set up with provider
- For custom endpoints, verify server is running

**"Models not loading":**

- Wait a moment and try refreshing
- Check if API key has correct permissions
- Verify base URL format (should end with `/v1/` for OpenAI-compatible APIs)

## Best Practices

### Model Selection

1. **Match complexity to task**
      - Don't use GPT-5-chat for simple formatting
      - Don't use GPT-5-nano for complex analysis

2. **Consider cost**
      - Fast models for high-volume tasks
      - Intelligent models for critical analysis

3. **Test different combinations**
      - Find the optimal balance for your use case

### Performance Optimization

1. **Use local models** for:
      - Sensitive data
      - High-volume processing
      - Offline operation

2. **Use cloud models** for:
      - Best quality
      - Latest capabilities
      - No infrastructure management

## Cost Management

### Monitoring Usage

- Track usage through provider dashboards
- Monitor job costs in UI
- Set up billing alerts
- Monitor token consumption in MAESTRO logs

## Common Configurations

### Budget-Conscious Setup
- **All models**: OpenRouter with open models (Mistral, Llama)
- **Cost**: Very low

### Quality-Focused Setup
- **Fast**: `GPT-5-nano` or `GPT-4o-mini` or `Claude Haiku`
- **Mid**: `GPT-5-mini` or `Claude Sonnet`
- **Intelligent**: `GPT-5-chat` or `Claude Opus`
- **Verifier**: same as Intelligent

### Privacy-Focused Setup
- **All models**: Local LLMs via VLLM or SGLang with structured generation
- **No external API calls**

### Hybrid Setup
- **Fast/Mid**: Local models
- **Intelligent**: Cloud model for complex tasks
- **Balance of privacy and capability**

## Provider Comparison

| Provider | Pros | Cons | Best For |
|----------|------|------|----------|
| OpenRouter | 100+ models, unified billing | Adds small overhead | Flexibility |
| OpenAI | Direct access, latest models | Single vendor | GPT users |
| Local LLMs | Privacy, no costs | Requires hardware | Sensitive data |

## Troubleshooting

### API Key Issues

**Invalid API key:**

- Double-check key from provider dashboard
- Ensure no extra spaces
- Verify key is active

**Rate limiting:**

- Check provider rate limits
- Implement retry logic
- Consider upgrading plan

### Model Selection Issues

**Model not available:**

- Verify model name spelling
- Check if model is available in your region
- Ensure API key has access to model

**Wrong model behavior:**

- Verify correct model selected
- Check model parameters
- Test with different model

## Next Steps

- [Search Provider Configuration](search-providers.md) - Set up web search
- [Environment Variables](environment-variables.md) - System configuration
- [First Login](../first-login.md) - Initial setup guide