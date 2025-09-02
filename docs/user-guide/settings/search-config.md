# Search Configuration

Configure web search providers for MAESTRO's research capabilities.

![Search Configuration Interface](//assets/images/settings/search.png)

## Overview

Web search providers enable MAESTRO to access current information from the internet, expanding research beyond your document library.

For detailed configuration instructions and provider comparisons, see the [Search Provider Configuration Guide](../../getting-started/configuration/search-providers.md).

## Quick Setup

1. **Navigate to Settings → Search**
2. **Select your provider** from the dropdown
3. **Enter credentials**:
      - API-based providers: Enter API key
      - SearXNG: Enter instance URL
4. **Configure search options** (if available)
5. **Click "Save & Close"**

## Supported Providers

### LinkUp (Recommended)
- Real-time comprehensive search
- Wide web coverage
- [Get API Key](https://linkup.com/dashboard)

### Tavily
- AI-optimized for LLM applications
- [Get API Key](https://app.tavily.com/home)

### Jina
- Advanced content extraction
- Free tier available
- [Get API Key](https://jina.ai/reader)

### SearXNG
- Privacy-focused, open-source
- No API limits (self-hosted)
- [Setup Instructions](../../getting-started/configuration/search-providers.md#searxng)

## Common Issues

- **No results**: Check API key, billing, and rate limits
- **SearXNG errors**: Verify URL and [JSON output configuration](../../getting-started/configuration/search-providers.md#configuration-requirements)
- **Poor quality**: Adjust search depth and query specificity

For comprehensive troubleshooting and best practices, see the [Search Provider Configuration Guide](../../getting-started/configuration/search-providers.md).

## Next Steps

- [AI Configuration](ai-config.md) - Configure language models
- [Research Settings](research-config.md) - Optimize research missions
- [Web Fetch Settings](web-fetch-config.md) - Configure web content fetching