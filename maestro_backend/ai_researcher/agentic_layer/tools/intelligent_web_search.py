"""
Intelligent Web Search Tool that analyzes queries and sets appropriate search parameters.
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class QueryAnalyzer:
    """Analyzes search queries to extract intent and parameters."""
    
    # Date patterns
    DATE_PATTERNS = {
        'year': r'\b(19|20)\d{2}\b',
        'month_year': r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(19|20)\d{2}\b',
        'last_n_days': r'\b(?:last|past)\s+(\d+)\s+days?\b',
        'last_n_months': r'\b(?:last|past)\s+(\d+)\s+months?\b',
        'last_n_years': r'\b(?:last|past)\s+(\d+)\s+years?\b',
        'since_year': r'\bsince\s+(19|20)\d{2}\b',
        'after_year': r'\bafter\s+(19|20)\d{2}\b',
        'before_year': r'\bbefore\s+(19|20)\d{2}\b',
        'recent': r'\b(?:recent|recently|latest|newest)\b',
        'between_years': r'\bbetween\s+(19|20)\d{2}\s+and\s+(19|20)\d{2}\b',
    }
    
    # Domain patterns  
    DOMAIN_HINTS = {
        'academic': ['arxiv.org', 'scholar.google.com', 'pubmed.ncbi.nlm.nih.gov', 'ieee.org', 'acm.org'],
        'news': ['reuters.com', 'bloomberg.com', 'nytimes.com', 'bbc.com', 'cnn.com'],
        'tech': ['github.com', 'stackoverflow.com', 'medium.com', 'techcrunch.com'],
        'medical': ['pubmed.ncbi.nlm.nih.gov', 'nih.gov', 'who.int', 'nejm.org'],
        'legal': ['law.cornell.edu', 'justia.com', 'findlaw.com'],
    }
    
    # Keywords that suggest depth of search needed
    DEPTH_KEYWORDS = {
        'advanced': ['comprehensive', 'detailed', 'in-depth', 'thorough', 'extensive', 'all', 'complete'],
        'standard': ['quick', 'brief', 'summary', 'overview', 'basic', 'simple']
    }
    
    # Keywords that suggest more results needed
    VOLUME_KEYWORDS = {
        'high': ['many', 'multiple', 'various', 'different', 'several', 'numerous', 'all available'],
        'low': ['few', 'couple', 'one or two', 'single', 'specific']
    }
    
    @classmethod
    def extract_date_range(cls, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract date range from query."""
        query_lower = query.lower()
        today = datetime.now()
        
        # Check for "recent" keywords (last 6 months)
        if re.search(cls.DATE_PATTERNS['recent'], query_lower):
            from_date = (today - timedelta(days=180)).strftime('%Y-%m-%d')
            return from_date, None
            
        # Check for "last N days"
        match = re.search(cls.DATE_PATTERNS['last_n_days'], query_lower)
        if match:
            days = int(match.group(1))
            from_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')
            return from_date, None
            
        # Check for "last N months"
        match = re.search(cls.DATE_PATTERNS['last_n_months'], query_lower)
        if match:
            months = int(match.group(1))
            from_date = (today - timedelta(days=months*30)).strftime('%Y-%m-%d')
            return from_date, None
            
        # Check for "last N years"
        match = re.search(cls.DATE_PATTERNS['last_n_years'], query_lower)
        if match:
            years = int(match.group(1))
            from_date = (today - timedelta(days=years*365)).strftime('%Y-%m-%d')
            return from_date, None
            
        # Check for "since YEAR"
        match = re.search(cls.DATE_PATTERNS['since_year'], query_lower)
        if match:
            year = match.group(1)
            from_date = f"{year}-01-01"
            return from_date, None
            
        # Check for "after YEAR"
        match = re.search(cls.DATE_PATTERNS['after_year'], query_lower)
        if match:
            year = match.group(1)
            from_date = f"{year}-12-31"
            return from_date, None
            
        # Check for "before YEAR"
        match = re.search(cls.DATE_PATTERNS['before_year'], query_lower)
        if match:
            year = match.group(1)
            to_date = f"{year}-01-01"
            return None, to_date
            
        # Check for "between YEAR and YEAR"
        match = re.search(cls.DATE_PATTERNS['between_years'], query_lower)
        if match:
            from_year = match.group(1)
            to_year = match.group(2)
            from_date = f"{from_year}-01-01"
            to_date = f"{to_year}-12-31"
            return from_date, to_date
            
        # Check for specific year
        years = re.findall(cls.DATE_PATTERNS['year'], query)
        if years:
            # If a specific year is mentioned, search within that year
            year = years[0]
            from_date = f"{year}-01-01"
            to_date = f"{year}-12-31"
            return from_date, to_date
            
        return None, None
    
    @classmethod
    def extract_domains(cls, query: str) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        """Extract domain preferences from query."""
        query_lower = query.lower()
        include_domains = []
        exclude_domains = []
        
        # Check for explicit domain mentions
        domain_pattern = r'(?:from|on|at|site:)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        matches = re.findall(domain_pattern, query_lower)
        if matches:
            include_domains.extend(matches)
        
        # Check for explicit exclusions
        exclude_pattern = r'(?:not from|exclude|except|without)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        matches = re.findall(exclude_pattern, query_lower)
        if matches:
            exclude_domains.extend(matches)
        
        # Check for topic-based domain suggestions
        if 'academic' in query_lower or 'research paper' in query_lower or 'journal' in query_lower:
            include_domains.extend(cls.DOMAIN_HINTS['academic'])
        elif 'news' in query_lower or 'article' in query_lower:
            include_domains.extend(cls.DOMAIN_HINTS['news'])
        elif 'technical' in query_lower or 'programming' in query_lower or 'code' in query_lower:
            include_domains.extend(cls.DOMAIN_HINTS['tech'])
        elif 'medical' in query_lower or 'health' in query_lower or 'clinical' in query_lower:
            include_domains.extend(cls.DOMAIN_HINTS['medical'])
        elif 'legal' in query_lower or 'law' in query_lower or 'court' in query_lower:
            include_domains.extend(cls.DOMAIN_HINTS['legal'])
        
        # Avoid sites like Wikipedia for academic searches
        if 'academic' in query_lower or 'research' in query_lower:
            exclude_domains.append('wikipedia.org')
            exclude_domains.append('wikihow.com')
        
        # Remove duplicates and return
        include_domains = list(set(include_domains)) if include_domains else None
        exclude_domains = list(set(exclude_domains)) if exclude_domains else None
        
        return include_domains, exclude_domains
    
    @classmethod
    def determine_search_depth(cls, query: str) -> str:
        """Determine if advanced or standard search depth is needed."""
        query_lower = query.lower()
        
        # Check for explicit depth keywords
        for keyword in cls.DEPTH_KEYWORDS['advanced']:
            if keyword in query_lower:
                return 'advanced'
        
        for keyword in cls.DEPTH_KEYWORDS['standard']:
            if keyword in query_lower:
                return 'standard'
        
        # Default to standard for most queries, advanced for complex ones
        # Complex queries have multiple clauses or specific requirements
        if len(query.split()) > 15 or ' and ' in query_lower or ' or ' in query_lower:
            return 'advanced'
        
        return 'standard'
    
    @classmethod
    def determine_result_count(cls, query: str) -> int:
        """Determine optimal number of results based on query."""
        query_lower = query.lower()
        
        # Check for explicit volume keywords
        for keyword in cls.VOLUME_KEYWORDS['high']:
            if keyword in query_lower:
                return 10  # Higher number of results
        
        for keyword in cls.VOLUME_KEYWORDS['low']:
            if keyword in query_lower:
                return 3  # Lower number of results
        
        # Default to 5
        return 5
    
    @classmethod
    def clean_query(cls, query: str) -> str:
        """Remove date/domain patterns from query for cleaner search."""
        cleaned = query
        
        # Remove date-related phrases
        patterns_to_remove = [
            cls.DATE_PATTERNS['last_n_days'],
            cls.DATE_PATTERNS['last_n_months'],
            cls.DATE_PATTERNS['last_n_years'],
            cls.DATE_PATTERNS['since_year'],
            cls.DATE_PATTERNS['after_year'],
            cls.DATE_PATTERNS['before_year'],
            r'(?:from|on|at|site:)\s*[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'(?:not from|exclude|except|without)\s*[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        ]
        
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        cleaned = ' '.join(cleaned.split())
        
        return cleaned

class IntelligentSearchInput(BaseModel):
    """Input schema for intelligent web search."""
    query: str = Field(..., description="The search query that will be analyzed for intelligent parameter extraction")
    override_max_results: Optional[int] = Field(None, description="Override the auto-determined result count")
    override_depth: Optional[str] = Field(None, description="Override the auto-determined search depth")
    mission_id: Optional[str] = Field(None, description="Mission ID for context-specific settings")

async def intelligent_web_search(
    query: str,
    override_max_results: Optional[int] = None,
    override_depth: Optional[str] = None,
    mission_id: Optional[str] = None,
    web_search_tool=None,
    **kwargs
) -> Dict[str, Any]:
    """
    Intelligently analyze the query and perform web search with optimal parameters.
    
    This function analyzes the user's query to extract:
    - Date ranges (from keywords like "recent", "last 5 years", "since 2020")
    - Domain preferences (academic sites, news sites, specific domains)
    - Search depth requirements (comprehensive vs quick search)
    - Optimal result count
    
    Args:
        query: The search query to analyze and execute
        override_max_results: Optional override for result count
        override_depth: Optional override for search depth
        mission_id: Optional mission ID for context
        web_search_tool: The web search tool instance to use
        
    Returns:
        Search results with metadata about the parameters used
    """
    if not web_search_tool:
        return {"error": "Web search tool not available"}
    
    # Analyze the query
    from_date, to_date = QueryAnalyzer.extract_date_range(query)
    include_domains, exclude_domains = QueryAnalyzer.extract_domains(query)
    depth = override_depth or QueryAnalyzer.determine_search_depth(query)
    max_results = override_max_results or QueryAnalyzer.determine_result_count(query)
    
    # Clean the query for better search results
    cleaned_query = QueryAnalyzer.clean_query(query)
    
    # Log the intelligent analysis
    logger.info(f"Intelligent search analysis for query: '{query}'")
    logger.info(f"  - Cleaned query: '{cleaned_query}'")
    logger.info(f"  - Date range: {from_date} to {to_date}")
    logger.info(f"  - Include domains: {include_domains}")
    logger.info(f"  - Exclude domains: {exclude_domains}")
    logger.info(f"  - Search depth: {depth}")
    logger.info(f"  - Max results: {max_results}")
    
    # Execute the search with analyzed parameters
    result = await web_search_tool.execute(
        query=cleaned_query,
        max_results=max_results,
        from_date=from_date,
        to_date=to_date,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        depth=depth,
        mission_id=mission_id,
        **kwargs
    )
    
    # Add metadata about the search parameters used
    if 'error' not in result:
        result['search_metadata'] = {
            'original_query': query,
            'cleaned_query': cleaned_query,
            'parameters_used': {
                'date_range': {'from': from_date, 'to': to_date} if from_date or to_date else None,
                'domains': {
                    'included': include_domains,
                    'excluded': exclude_domains
                } if include_domains or exclude_domains else None,
                'depth': depth,
                'max_results': max_results
            }
        }
    
    return result