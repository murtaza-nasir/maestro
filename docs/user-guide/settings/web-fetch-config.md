# Web Fetch Configuration

Configure how MAESTRO fetches and processes content from web pages discovered during research.

![Web Fetch Settings](../../assets/images/settings/web-fetch.png)

## Overview

Web fetching extracts full content from web pages found during searches, enabling MAESTRO to read entire articles beyond search snippets.

## Quick Setup

1. **Navigate to Settings → Web Fetch**
2. **Select fetch provider** (Original + Jina Fallback recommended)
3. **Configure Jina settings** if using Jina features
4. **Adjust timeout and options** as needed
5. **Click "Save & Close"**

## Fetch Providers

### Original + Jina Fallback (Recommended)

Built-in fetcher with automatic Jina fallback for problematic sites.

**How it Works:**

1. First attempts with built-in fetcher (fast)
2. On 403 errors or blocks, automatically uses Jina
3. Best of both worlds approach

**Best For:**

- Most use cases
- Balanced speed and reliability
- Automatic handling of difficult sites

### Original (Built-in Fetcher)

- **Fast and free** - No API limits or costs
- **Limited** - Can't handle JavaScript sites, many sites block bot access
- **Best for** - Static HTML, news articles, documentation

### Jina Reader API

- **Advanced** - Handles JavaScript and complex sites
- **Requires API key** - Get from [jina.ai](https://jina.ai)
- **Best for** - JavaScript apps, sites that block scrapers

## Jina Configuration Options

### Browser Engine
- **Default** - Balanced speed and quality
- **Fast** - Quick but may miss dynamic content
- **Complete** - Thorough but slower

### Content Format
- **Markdown** (Recommended) - Structured, clean format
- **HTML** - Raw output for special needs
- **Text** - Plain text, smallest size

### Timeout Settings

- Simple sites: 10-15 seconds
- Complex sites: 30 seconds
- Heavy apps: 45-60 seconds

### Processing Options

- **Gather links** - Extract all hyperlinks
- **Gather images** - Collect image URLs

## Configuration Tips

### For Speed

- Use Original fetcher
- Short timeouts (10-15s)
- Fast browser engine

### For Quality

- Use Jina Reader
- Longer timeouts (30-45s)
- Complete browser mode

### For Cost Efficiency

- Use Original + Jina fallback
- Cache fetched content

## Troubleshooting

- **403 Errors**: Switch to Jina
- **Incomplete Content**: Increase timeout, use Complete mode
- **Slow Fetching**: Reduce timeout, use Fast mode
- **Format Issues**: Try Markdown format, enable link gathering

## Provider Comparison

| Feature | Original | Jina | Original + Fallback |
|---------|----------|------|-------------------|
| Speed | Fast | Slow | Variable |
| JavaScript | No | Yes | Yes (fallback) |
| Cost | Free | Paid | Minimal |
| Reliability | medium | high | high |
| Setup | None | API Key | API Key |

## Next Steps

After configuring web fetch:

1. Set up [Research Parameters](research-config.md)
2. Test with various website types
3. Monitor performance and costs
4. Optimize based on usage patterns