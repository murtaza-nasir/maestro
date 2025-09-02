# Search Provider Configuration

Enable web search capabilities for MAESTRO's research agents to access current information from the internet.

![Search Configuration Interface](//assets/images/settings/search.png)

## Overview

Web search providers allow MAESTRO to:

- Find current information beyond training data
- Discover recent research and developments
- Verify facts with multiple sources
- Expand research beyond your document library

## Supported Search Providers

### Tavily

AI-powered search specifically designed for LLM applications.

**Configuration:**

- **Provider**: Select "Tavily" from dropdown
- **API Key**: Get from [Tavily Dashboard](https://app.tavily.com/home)
- **Format**: `tvly-...`

### LinkUp (Recommended)

Real-time search API with comprehensive web coverage.

**Configuration:**

- **Provider**: Select "LinkUp" from dropdown
- **API Key**: Get from [LinkUp Dashboard](https://linkup.com/dashboard)
- **Format**: `7a8d9e1b-...`

### Jina

Advanced AI-powered search with content extraction capabilities.

**Configuration:**

- **Provider**: Select "Jina" from dropdown
- **API Key**: Get from [Jina Dashboard](https://jina.ai/reader)
- **Format**: `jina_...`

### SearXNG

Open-source metasearch engine that aggregates results from multiple search engines.

**Features:**

- Privacy-focused (no tracking)
- No API limits on self-hosted instances
- Aggregates 70+ search engines
- Customizable search categories

**Configuration:**

- **Provider**: Select "SearXNG" from dropdown
- **Base URL**: Your SearXNG instance URL
    - Example: `https://searxng.example.com`
    - Public instance: `https://search.brave.com`
- **No API Key Required**
- **Categories**: Select search categories (optional)
    - General
    - Images
    - News
    - Science
    - IT
    - Map
    - Music
    - Files
    - Social Media

**Setup Options:**

#### Using Public Instance
1. Find a public instance from [SearXNG Instances](https://searx.space/)
2. Enter the URL in Base URL field
3. Ensure instance supports JSON output

#### Self-Hosting with Docker
```bash
# Quick setup
docker run -d \
  --name searxng \
  -p 8080:8080 \
  -e SEARXNG_BASE_URL=http://localhost:8080 \
  searxng/searxng:latest

# Access at http://localhost:8080
```

#### Configuration Requirements
- Instance must be configured to output JSON format
- Enable JSON format in SearXNG settings:
  ```yaml
  # In searxng/settings.yml
  search:
    formats:
      - json
      - html
  ```

**Best For:**

- Privacy-conscious users
- Unlimited searches (self-hosted)
- Comprehensive results from multiple sources
- Organizations wanting full control

## Search Configuration Settings

Depending on your provider, you may configure:

- **Results per query** - Number of results to fetch
- **Language preference** - Filter results by language
- **Region settings** - Geographic filtering
- **Time range** - Recent vs all-time results

## Setting Up Search

### Step 1: Choose Your Provider

Consider these factors:

| Factor | Tavily | LinkUp | Jina | SearXNG |
|--------|--------|--------|------|---------|
| **Cost** | Free tier, then paid | Free tier, then paid | Free tier available | Free (self-hosted) |
| **Privacy** | API calls logged | API calls logged | API calls logged | Full privacy |
| **Quality** | AI-optimized | Good general results | Advanced extraction | Varies by engines |
| **Setup** | API key only | API key only | API key only | Instance required |
| **Limits** | Based on plan | Based on plan | Based on plan | None (self-hosted) |

### Step 2: Configure Provider

1. Navigate to **Settings → Search**
2. Select provider from dropdown
3. Enter credentials:
    - **API-based**: Enter your API key
    - **SearXNG**: Enter instance URL
4. Configure search depth if needed
5. Click **Save & Close**

### Step 3: Test Configuration

1. Go to Research or Writing tab
2. Start a new chat
3. Ask a question requiring web search
4. Verify results are returned

## Usage in MAESTRO

### In Research Missions

Web search usage helps when:

- Information isn't in your documents
- Current information is needed
- Verification of facts is required

### In Writing Mode

Configure search parameters:

- Search iterations
- Number of queries
- Results per search
- Deep search toggle

### Search Integration

MAESTRO intelligently combines:

- Document search (your library)
- Web search (configured provider)
- Result reranking

## Troubleshooting

### No Search Results

**Check these issues:**

1. **API Key**: Verify it's correct and active
2. **Billing**: Ensure account has credits/active subscription
3. **Rate Limits**: Check if you've exceeded limits
4. **Network**: Verify internet connectivity

### SearXNG Specific Issues

**"Connection failed":**

- Verify URL is correct (with or without trailing slash)
- Check instance is accessible
- Ensure JSON output is enabled (see [Configuration Requirements](#configuration-requirements) above)

**"No results":**

- Select at least one search category
- Try a different public instance
- Check instance is functioning

### Poor Result Quality

**Improve results by:**

1. Adjusting search depth
2. Using more specific queries
3. Trying a different provider
4. Configuring language/region settings

## Best Practices

### Provider Selection

1. **For Research**: Linkup or Jina 
2. **For Privacy**: SearXNG (self-hosted)
3. **For General Use**: Linkup 
4. **For Budget**: SearXNG or free tiers

### Query Optimization

- Use specific, descriptive queries
- Include relevant context
- Specify time ranges when needed
- Use appropriate search depth

### Cost Management

1. **Monitor usage** through provider dashboards
2. **Set alerts** for usage thresholds
3. **Use SearXNG** for unlimited searches
4. **Optimize search depth** to reduce API calls

## Security Considerations

### Privacy Implications

- **API Providers**: Log searches and IP
- **SearXNG Self-Hosted**: Complete privacy
- **Public SearXNG**: Check instance privacy policy

## Next Steps

- [Environment Variables](environment-variables.md) - System configuration
- [AI Provider Configuration](ai-providers.md) - LLM setup
- [First Login](../first-login.md) - Initial setup guide
- [Research Configuration](../../user-guide/settings/research-config.md) - Optimize search usage