# AI Model Troubleshooting

Quick fixes for AI model configuration and API issues.

## Configuration Issues

### No Models in Dropdown

**Solution:**

1. Go to Settings → AI Config
2. Select provider (OpenAI, OpenRouter, or Custom Provider)
3. Enter API key
4. Click "Test" button
5. Models should populate automatically

![AI Config Model Selection](../../assets/images/troubleshooting/ai-config-model-selection.png)

**If still empty:**
```bash
# Check logs for errors
docker compose logs maestro-backend | grep -i "api\|model"

# Restart backend
docker compose restart maestro-backend
```

### Wrong Model Being Used

**Check current configuration:**

1. Go to Settings → AI Config
2. Verify each model type is set correctly:
   - Fast Model: For quick tasks
   - Mid Model: For balanced performance
   - Intelligent Model: For complex analysis
   - Verifier Model: For verification

## API Issues

### Authentication Failed

**Error:** Invalid API key

**Solution:**
```bash
# Test OpenAI key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"

# Test OpenRouter key
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Rate Limit Errors

**Error:** Rate limit exceeded

**Solution:**
```bash
# Configure retry settings in .env
MAX_RETRIES=3
RETRY_DELAY=5
MAX_CONCURRENT_REQUESTS=2

# Restart
docker compose restart maestro-backend
```

### Context Too Large

**Error:** Context length exceeded

**Solution in Settings → Research:**

- Reduce `writing_agent_max_context_chars` (e.g., 100,000)
- Reduce `main_research_doc_results` (e.g., 3)
- Reduce `main_research_web_results` (e.g., 3)

## Provider-Specific Issues

### OpenAI

**Common issues:**

- Wrong API key format
- Insufficient credits
- Model not available in your region

**Check account:**
```bash
# Check usage
curl https://api.openai.com/v1/usage \
  -H "Authorization: Bearer YOUR_KEY"
```

### OpenRouter

**Model not found:**
```bash
# Use full model path
# Correct: anthropic/claude-3-sonnet
# Wrong: claude-3-sonnet

# Check available models
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer YOUR_KEY"
```

### Custom Provider

**Connection failed:**
```bash
# Test endpoint
curl YOUR_CUSTOM_BASE_URL/v1/models

# Common base URLs:
# Local vLLM: http://localhost:5000/v1
# Local SGLang: http://localhost:30000/v1
# Local Ollama: http://localhost:11434/v1
# LM-Studio: http://localhost:1234/v1
```

## Performance Issues

### Slow Response

**Quick fixes:**

1. Use faster models (e.g., gpt-4o-mini)
2. Reduce context sizes in Research settings
3. Check network latency to API

### High Costs

**Reduce costs:**

1. Use cheaper models for Fast/Mid tiers
2. Reduce research parameters:
    - `initial_research_max_questions`
    - `structured_research_rounds`
    - `writing_passes`

## Cost Tracking Discrepancies

### Why Don't My Tracked Costs Match My API Provider Dashboard?

This is a known issue with some API providers' pricing and billing. MAESTRO correctly tracks costs based on providers' advertised pricing, but actual charges often differ significantly.

#### The Problem

Some API providers, particularly aggregators/routers, have inconsistent billing:

1. **API aggregators route to different providers** - Each backend provider may have different actual costs
2. **Dynamic routing affects pricing** - Aggregators choose providers based on availability and latency, not just price
3. **API `usage.cost` field may be unreliable** - Sometimes returns values ~100x lower than actual charges
4. **Dashboard charges don't match advertised pricing** - Can be 0.4x to 4x the calculated cost

#### Real Example

Here's actual data from testing with a popular model:

| Prompt Tokens | Completion | Our Calculation | API usage.cost | Dashboard Charge | Variance |
|--------------|------------|-----------------|----------------|------------------|----------|
| 4,405 | 200 | $0.000601 | $0.000006 | $0.000594 | 0.99x |
| 349 | 300 | $0.000275 | $0.000003 | $0.000272 | 0.99x |
| 52 | 1,000 | $0.000805 | $0.000003 | $0.000312 | **0.39x** |
| 243 | 200 | $0.000184 | $0.000003 | $0.000331 | **1.80x** |
| 64 | 124 | $0.000106 | $0.000002 | $0.000157 | **1.48x** |

**Key Findings:**

- Token counts are usually accurate across API and dashboard 
- MAESTRO's pricing calculation is correct based on advertised rates 
- Dashboard charges can be inconsistent with advertised rates 

#### Testing Your Own Costs

We provide a test script to verify pricing discrepancies:

```bash
# Run the pricing test (example for OpenRouter)
python scripts/test_openrouter_pricing.py --api-key YOUR_API_KEY

# Example output will show:
# - Token counts from API
# - Calculated costs based on advertised pricing
# - API reported costs (usually wrong)
# - Comparison with dashboard charges
```

#### What This Means for You

1. **Your tracked costs may differ from actual charges** - typically 40-60% of dashboard values
2. **This is NOT a bug in MAESTRO** - we calculate correctly based on advertised prices
3. **Some providers' billing is inconsistent** - they may charge differently than advertised

#### Workarounds

1. **Apply a multiplier** to displayed costs based on your provider:
   ```python
   # Adjust based on your observed discrepancy
   estimated_actual_cost = tracked_cost * 1.5
   ```

2. **Monitor your actual provider dashboard** for true costs

3. **Use providers with consistent pricing** if cost accuracy is critical:
   - Some providers have more predictable pricing than others
   - Local models have zero API costs

#### Technical Details

The discrepancy may be caused by:

- **Aggregator routing**: Services like OpenRouter route to different backend providers with varying costs
- **Dynamic provider selection**: Aggregators optimize for availability and latency, not just price
- **Hidden tokens**: Providers may count system prompts or special tokens not reported in API
- **Different tokenizers**: Billing tokenizer may differ from API response tokenizer  
- **Overhead charges**: Routing or processing overhead not disclosed
- **Minimum charges or rounding**: Some providers may have minimum charge amounts

**Note**: Direct providers (like OpenAI, Anthropic) typically have more consistent pricing than aggregators/routers, as they don't route between multiple backends.

For more technical details and provider-specific test scripts, see our [scripts directory](https://github.com/murtaza-nasir/maestro/tree/main/scripts).

## Debugging

### Enable Debug Logging

```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker compose restart maestro-backend

# Watch logs
docker compose logs -f maestro-backend | grep -i "model\|api"
```

### Test Models Directly

```bash
# Check configured models
docker exec maestro-backend python -c "
from ai_researcher.dynamic_config import get_fast_model_name, get_mid_model_name, get_intelligent_model_name
print('Fast:', get_fast_model_name())
print('Mid:', get_mid_model_name())
print('Intelligent:', get_intelligent_model_name())
"
```

## Structured Outputs & Provider Compatibility

### What are Structured Outputs?

Maestro uses OpenAI's structured outputs feature (`json_schema` response format) to ensure LLM responses match exact Pydantic model schemas. However, not all providers support this advanced feature.

### Provider Support Status

| Provider | json_object | json_schema (Structured) | Notes |
|----------|------------|-------------------------|--------|
| **OpenAI** | ✅ | ✅ | Full support (gpt-4o 2024-08-06+) |
| **Azure OpenAI** | ✅ | ⚠️ | Needs model 2024-08-06+, API 2024-10-21+ |
| **Anthropic Claude** | ✅ | ✅ | Full support via different API |
| **Google Gemini** | ✅ | ⚠️ | Limited support, different implementation |
| **DeepSeek** | ✅ | ❌ | Only basic json_object mode |
| **Moonshot/Kimi** | ⚠️ | ❌ | Own incompatible JSON schema format |
| **Local (Ollama)** | ✅ | ❌ | Most models only support json_object |
| **Local (LM-Studio)** | ✅ | ❌ | Basic JSON mode only |
| **Local (vLLM)** | ✅ | ✅ | Full support with `guided_json` parameter ([docs](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#extra-parameters)) |
| **Local (SGLang)** | ✅ | ✅ | Full support with grammar constraints ([docs](https://sgl-project.github.io/references/sampling_params.html#json-decoding)) |

### Automatic Fallback Mechanism

Maestro automatically handles incompatible providers:

1. **First attempts** structured outputs for maximum reliability
2. **Detects errors** and falls back to `json_object` mode
3. **Enhances prompts** with schema instructions in fallback mode
4. **Validates responses** against Pydantic models regardless

### Common Compatibility Errors

| Error Message | Provider | Meaning |
|--------------|----------|---------|
| "This response_format type is unavailable" | DeepSeek | No json_schema support |
| "Invalid moonshot flavored json schema" | Moonshot/Kimi | Incompatible schema format |
| "keyword 'default' is not allowed" | Moonshot | Schema validation error |
| "structured outputs are not supported" | Azure (older) | Need newer model/API |

### Configuring Local Model Servers

#### vLLM with Structured Outputs
```bash
# Start vLLM with guided decoding
python -m vllm.entrypoints.openai.api_server \
  --model your-model \
  --guided-decoding-backend outlines \
  --port 5000

# In Maestro Settings → AI Config:
# Provider: Custom Provider
# Base URL: http://localhost:5000/v1
# Model: your-model
```

#### SGLang with Grammar Support
```bash
# Start SGLang server
python -m sglang.launch_server \
  --model-path your-model \
  --port 30000

# In Maestro Settings → AI Config:
# Provider: Custom Provider  
# Base URL: http://localhost:30000/v1
# Model: your-model
```

For detailed local LLM deployment, see [Local LLM Deployment Guide](../../deployment/local-llms.md).

## Common Error Messages

| Error | Solution |
|-------|----------|
| "API key invalid" | Check key in Settings → AI Config |
| "Model not found" | Use full model path (provider/model) |
| "Rate limit exceeded" | Wait or upgrade API plan |
| "Context length exceeded" | Reduce context in Research settings |
| "Connection timeout" | Check network/firewall |
| "Invalid json schema" | Provider doesn't support structured outputs (auto-fallback) |
| "response_format unavailable" | Provider limitation (auto-fallback) |

## Quick Fixes

### Reset AI Configuration

```bash
# Clear settings and reconfigure
docker exec maestro-postgres psql -U maestro_user -d maestro_db -c "
UPDATE users SET settings = settings - 'ai_endpoints' WHERE username = 'admin';
"

# Then reconfigure in web UI
```

### Switch to Local Models

```bash
# In Settings → AI Config
# Select "Custom Provider"
# Base URL: http://your-server:5000/v1
# Model: localmodel
```

## Still Having Issues?

1. Check logs: `docker compose logs maestro-backend`
2. Verify API keys are valid
3. Check provider status pages
4. Try different models