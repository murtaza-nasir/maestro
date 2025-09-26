"""
ArXiv Paper Fetcher Tool

This tool specifically handles arXiv paper URLs and fetches papers in multiple formats.
It detects arXiv URLs and uses various methods to get the best quality content:
1. ar5iv HTML (best) - Clean HTML version with proper formatting
2. LaTeX source - Original source that can be processed
3. PDF fallback - When other methods fail
"""

import logging
import re
import asyncio
import aiohttp
import fitz  # PyMuPDF
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, Callable, List, Tuple
import queue
import hashlib
import datetime
import pathlib
import json
import os
import tarfile
import gzip
import io
from bs4 import BeautifulSoup
import html2text

logger = logging.getLogger(__name__)

# Cache directory for arXiv papers
CACHE_DIR = pathlib.Path("ai_researcher/data/arxiv_cache/")

class ArXivFetcherTool:
    """
    Specialized tool for fetching arXiv papers.
    Handles various arXiv URL formats and fetches both metadata and full PDF content.
    """
    
    # Regex patterns for arXiv URLs
    ARXIV_PATTERNS = [
        r'(?:https?://)?arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)',  # New format: 2312.12345
        r'(?:https?://)?arxiv\.org/abs/([a-z\-]+/\d{7}(?:v\d+)?)',  # Old format: cs.AI/0301234
        r'(?:https?://)?arxiv\.org/html/(\d{4}\.\d{4,5}(?:v\d+)?)',  # HTML version new format
        r'(?:https?://)?arxiv\.org/html/([a-z\-]+/\d{7}(?:v\d+)?)',  # HTML version old format
        r'(?:https?://)?arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)',  # PDF link new format
        r'(?:https?://)?arxiv\.org/pdf/([a-z\-]+/\d{7}(?:v\d+)?)',  # PDF link old format
        r'(?:https?://)?ar5iv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)',  # ar5iv mirror
        r'(?:https?://)?ar5iv\.org/html/(\d{4}\.\d{4,5}(?:v\d+)?)',  # ar5iv HTML version
    ]
    
    def __init__(self):
        self.name = "arxiv_fetch_paper"
        self.description = "Fetches arXiv papers including full PDF content and metadata"
        
        # Ensure cache directory exists
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"ArXiv cache directory ensured at: {CACHE_DIR.resolve()}")
        except Exception as e:
            logger.error(f"Failed to create arXiv cache directory {CACHE_DIR}: {e}", exc_info=True)
    
    @classmethod
    def is_arxiv_url(cls, url: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a URL is an arXiv URL and extract the paper ID.
        
        Returns:
            Tuple of (is_arxiv, paper_id)
        """
        for pattern in cls.ARXIV_PATTERNS:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                paper_id = match.group(1)
                # Normalize paper ID (remove version if needed for API)
                base_id = paper_id.split('v')[0] if 'v' in paper_id else paper_id
                return True, base_id
        return False, None
    
    async def fetch_arxiv_metadata(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata from arXiv API.
        
        Args:
            arxiv_id: The arXiv paper ID
            
        Returns:
            Dictionary with paper metadata or None if failed
        """
        api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch arXiv metadata: HTTP {response.status}")
                        return None
                    
                    xml_content = await response.text()
                    
            # Parse XML response
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            # Find the entry
            entry = root.find('atom:entry', namespaces)
            if entry is None:
                logger.warning(f"No entry found for arXiv ID: {arxiv_id}")
                return None
            
            # Extract metadata
            metadata = {
                'arxiv_id': arxiv_id,
                'title': entry.findtext('atom:title', '', namespaces).strip(),
                'abstract': entry.findtext('atom:summary', '', namespaces).strip(),
                'published': entry.findtext('atom:published', '', namespaces),
                'updated': entry.findtext('atom:updated', '', namespaces),
                'authors': [],
                'categories': [],
                'pdf_url': f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                'abs_url': f"https://arxiv.org/abs/{arxiv_id}"
            }
            
            # Extract authors
            for author in entry.findall('atom:author', namespaces):
                name = author.findtext('atom:name', '', namespaces).strip()
                if name:
                    metadata['authors'].append(name)
            
            # Extract categories
            for category in entry.findall('atom:category', namespaces):
                term = category.get('term')
                if term:
                    metadata['categories'].append(term)
            
            # Extract comment (often contains conference info)
            comment = entry.findtext('arxiv:comment', '', namespaces)
            if comment:
                metadata['comment'] = comment.strip()
            
            # Extract journal reference if available
            journal_ref = entry.findtext('arxiv:journal_ref', '', namespaces)
            if journal_ref:
                metadata['journal_ref'] = journal_ref.strip()
            
            # Parse publication year from published date
            if metadata['published']:
                try:
                    pub_date = datetime.datetime.fromisoformat(metadata['published'].replace('Z', '+00:00'))
                    metadata['publication_year'] = pub_date.year
                except:
                    pass
            
            logger.info(f"Successfully fetched metadata for arXiv paper: {metadata['title']}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error fetching arXiv metadata for {arxiv_id}: {e}", exc_info=True)
            return None
    
    async def fetch_ar5iv_html(self, arxiv_id: str) -> Optional[str]:
        """
        Fetch the HTML version from ar5iv (HTML rendering of arXiv papers).
        ar5iv provides clean, accessible HTML versions of papers.
        
        Args:
            arxiv_id: The arXiv paper ID
            
        Returns:
            Extracted text from HTML or None if failed
        """
        # Try both ar5iv.labs.arxiv.org and arxiv.org/html (which redirects to ar5iv)
        ar5iv_urls = [
            f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
            f"https://arxiv.org/html/{arxiv_id}"
        ]
        
        for ar5iv_url in ar5iv_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    async with session.get(ar5iv_url, headers=headers, timeout=30) as response:
                        if response.status != 200:
                            logger.debug(f"ar5iv not available at {ar5iv_url}: HTTP {response.status}")
                            continue
                        
                        html_content = await response.text()
                        
                        # Check if we got a real paper or an error/template page
                        if "You will be analyzing" in html_content or "paper_summaries" in html_content:
                            logger.warning(f"Got template/prompt content instead of paper from {ar5iv_url}")
                            continue
                        
                        # Parse HTML and extract text
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # Remove script, style, and navigation elements
                        for element in soup(["script", "style", "nav", "header", "footer"]):
                            element.decompose()
                        
                        # Try to find the main article content
                        main_content = None
                        
                        # Look for specific ar5iv/arxiv HTML structure
                        for selector in ['article', 'div.ltx_document', 'main', 'div#main-content']:
                            main_content = soup.select_one(selector)
                            if main_content:
                                break
                        
                        if not main_content:
                            main_content = soup.find('body')
                        
                        if main_content:
                            # Convert to markdown for better formatting
                            h = html2text.HTML2Text()
                            h.ignore_links = False
                            h.ignore_images = True
                            h.body_width = 0  # Don't wrap lines
                            h.skip_internal_links = True
                            
                            text = h.handle(str(main_content))
                            
                            # Sanity check - make sure we got real content
                            if len(text) < 1000:
                                logger.warning(f"Extracted text too short ({len(text)} chars) from {ar5iv_url}")
                                continue
                                
                            logger.info(f"Successfully extracted text from ar5iv for {arxiv_id} ({len(text)} chars)")
                            return text
                        else:
                            logger.warning(f"Could not find main content in HTML from {ar5iv_url}")
            except asyncio.TimeoutError:
                logger.debug(f"Timeout while fetching {ar5iv_url}")
            except Exception as e:
                logger.debug(f"Error fetching {ar5iv_url}: {e}")
        
        return None
    
    async def fetch_arxiv_source(self, arxiv_id: str) -> Optional[str]:
        """
        Fetch the LaTeX/TeX source from arXiv.
        
        Args:
            arxiv_id: The arXiv paper ID
            
        Returns:
            Extracted text from source or None if failed
        """
        source_url = f"https://arxiv.org/e-print/{arxiv_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(source_url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        logger.debug(f"Source not available for {arxiv_id}: HTTP {response.status}")
                        return None
                    
                    # The source can be a .tar.gz, .gz, or plain .tex file
                    content = await response.read()
                    
                    # Try to process as tar.gz first (most common)
                    try:
                        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as tar:
                            tex_content = []
                            for member in tar.getmembers():
                                if member.name.endswith('.tex'):
                                    f = tar.extractfile(member)
                                    if f:
                                        tex_content.append(f.read().decode('utf-8', errors='ignore'))
                            
                            if tex_content:
                                # Combine all .tex files
                                combined = '\n\n'.join(tex_content)
                                # Clean LaTeX to extract readable text
                                text = self._clean_latex_to_text(combined)
                                logger.info(f"Extracted text from LaTeX source for {arxiv_id} ({len(text)} chars)")
                                return text
                    except:
                        pass
                    
                    # Try as gzipped single file
                    try:
                        content = gzip.decompress(content).decode('utf-8', errors='ignore')
                        text = self._clean_latex_to_text(content)
                        logger.info(f"Extracted text from gzipped LaTeX for {arxiv_id} ({len(text)} chars)")
                        return text
                    except:
                        pass
                    
                    # Try as plain text/LaTeX
                    try:
                        content = content.decode('utf-8', errors='ignore')
                        text = self._clean_latex_to_text(content)
                        logger.info(f"Extracted text from plain LaTeX for {arxiv_id} ({len(text)} chars)")
                        return text
                    except:
                        pass
                    
                    logger.debug(f"Could not process source format for {arxiv_id}")
                    return None
                    
        except Exception as e:
            logger.debug(f"Error fetching arXiv source for {arxiv_id}: {e}")
            return None
    
    def _clean_latex_to_text(self, latex_content: str) -> str:
        """
        Clean LaTeX content to extract readable text.
        This is a simple implementation that removes common LaTeX commands.
        
        Args:
            latex_content: Raw LaTeX content
            
        Returns:
            Cleaned text
        """
        # Remove comments
        text = re.sub(r'%.*?\n', '\n', latex_content)
        
        # Remove common LaTeX commands but keep their content
        patterns = [
            (r'\\begin\{[^}]+\}', ''),
            (r'\\end\{[^}]+\}', ''),
            (r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1'),  # Commands with arguments
            (r'\\[a-zA-Z]+\*?\s*', ' '),  # Commands without arguments
            (r'\$[^\$]+\$', '[MATH]'),  # Inline math
            (r'\$\$[^\$]+\$\$', '[EQUATION]'),  # Display math
            (r'\\item', '\n• '),
            (r'\\\\', '\n'),
            (r'~', ' '),
            (r'\\&', '&'),
            (r'\\_', '_'),
            (r'\\%', '%'),
            (r'\\#', '#'),
            (r'\\\$', '$'),
            (r'\\{', '{'),
            (r'\\}', '}'),
        ]
        
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        
        # Remove extra whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return text.strip()
    
    async def fetch_arxiv_pdf(self, arxiv_id: str) -> Optional[bytes]:
        """
        Fetch the PDF content from arXiv (fallback method).
        
        Args:
            arxiv_id: The arXiv paper ID
            
        Returns:
            PDF content as bytes or None if failed
        """
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(pdf_url, headers=headers, timeout=60) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch arXiv PDF: HTTP {response.status}")
                        return None
                    
                    pdf_content = await response.read()
                    logger.info(f"Successfully fetched PDF for arXiv paper {arxiv_id} ({len(pdf_content)} bytes)")
                    return pdf_content
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching arXiv PDF for {arxiv_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching arXiv PDF for {arxiv_id}: {e}", exc_info=True)
            return None
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """
        Extract text from PDF bytes using PyMuPDF.
        
        Args:
            pdf_bytes: PDF content as bytes
            
        Returns:
            Extracted text as string
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text("text") + "\n"
            doc.close()
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
            return ""
    
    async def execute(
        self,
        url: str,
        update_callback: Optional[Callable] = None,
        log_queue: Optional[queue.Queue] = None,
        mission_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the arXiv paper fetching.
        
        Args:
            url: The arXiv URL
            update_callback: Optional callback for updates
            log_queue: Optional queue for logging
            mission_id: Optional mission ID
            
        Returns:
            Dictionary with paper content and metadata
        """
        # Check if this is an arXiv URL
        is_arxiv, arxiv_id = self.is_arxiv_url(url)
        if not is_arxiv or not arxiv_id:
            return {"error": f"Not an arXiv URL: {url}"}
        
        logger.info(f"Processing arXiv paper: {arxiv_id} from URL: {url}")
        
        # Check cache first
        cache_key = hashlib.sha256(f"arxiv_{arxiv_id}".encode()).hexdigest()
        cache_content_path = CACHE_DIR / f"{cache_key}.pdf"
        cache_meta_path = CACHE_DIR / f"{cache_key}.meta.json"
        cache_text_path = CACHE_DIR / f"{cache_key}.txt"
        
        # Try to load from cache
        if cache_content_path.exists() and cache_meta_path.exists() and cache_text_path.exists():
            try:
                # Check cache age (7 days for arXiv papers)
                mod_time = datetime.datetime.fromtimestamp(
                    os.path.getmtime(cache_content_path), 
                    tz=datetime.timezone.utc
                )
                age = datetime.datetime.now(datetime.timezone.utc) - mod_time
                
                if age < datetime.timedelta(days=7):
                    logger.info(f"Cache hit for arXiv paper {arxiv_id}")
                    
                    with open(cache_meta_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    with open(cache_text_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    
                    return {
                        "text": text,
                        "title": metadata.get("title", f"arXiv:{arxiv_id}"),
                        "metadata": metadata,
                        "source": "arxiv_cache"
                    }
                else:
                    logger.info(f"Cache expired for arXiv paper {arxiv_id}")
            except Exception as e:
                logger.warning(f"Error reading cache for arXiv paper {arxiv_id}: {e}")
        
        # Send start feedback
        if update_callback and log_queue:
            try:
                update_callback(log_queue, {
                    "type": "arxiv_fetch_start",
                    "url": url,
                    "arxiv_id": arxiv_id
                })
            except Exception as e:
                logger.debug(f"Failed to send start feedback: {e}")
        
        # Fetch metadata and content
        try:
            # Fetch metadata first
            metadata = await self.fetch_arxiv_metadata(arxiv_id)
            if not metadata:
                return {"error": f"Failed to fetch metadata for arXiv paper {arxiv_id}"}
            
            # Try different methods to get the paper content
            text = None
            fetch_method = "unknown"
            
            # Method 1: Try ar5iv HTML (best quality)
            logger.info(f"Trying ar5iv HTML for {arxiv_id}...")
            text = await self.fetch_ar5iv_html(arxiv_id)
            if text:
                fetch_method = "ar5iv_html"
                logger.info(f"Successfully fetched paper via ar5iv HTML")
            
            # Method 2: Try LaTeX source
            if not text:
                logger.info(f"Trying LaTeX source for {arxiv_id}...")
                text = await self.fetch_arxiv_source(arxiv_id)
                if text:
                    fetch_method = "latex_source"
                    logger.info(f"Successfully fetched paper via LaTeX source")
            
            # Method 3: Fallback to PDF
            if not text:
                logger.info(f"Falling back to PDF for {arxiv_id}...")
                pdf_content = await self.fetch_arxiv_pdf(arxiv_id)
                if pdf_content:
                    text = self.extract_text_from_pdf(pdf_content)
                    if text:
                        fetch_method = "pdf"
                        logger.info(f"Successfully fetched paper via PDF")
                    # Cache the PDF even if text extraction fails
                    try:
                        pdf_cache_path = CACHE_DIR / f"{cache_key}.pdf"
                        with open(pdf_cache_path, 'wb') as f:
                            f.write(pdf_content)
                    except Exception as e:
                        logger.warning(f"Failed to cache PDF: {e}")
            
            if not text:
                return {"error": f"Failed to extract text from arXiv paper {arxiv_id} using any method"}
            
            # Format metadata for the standard extractor format
            # Convert lists to strings for compatibility with Note schema
            authors_str = ", ".join(metadata["authors"]) if metadata["authors"] else None
            keywords_str = ", ".join(metadata.get("categories", [])) if metadata.get("categories") else None
            
            formatted_metadata = {
                "title": metadata["title"],
                "authors": authors_str,  # Convert list to string
                "journal_or_source": "arXiv",
                "publication_year": metadata.get("publication_year"),
                "abstract": metadata["abstract"],
                "keywords": keywords_str,  # Convert list to string
                "arxiv_id": arxiv_id,
                "url": url,
                "pdf_url": metadata["pdf_url"],
                "comment": metadata.get("comment"),
                "journal_ref": metadata.get("journal_ref"),
                "fetch_method": fetch_method,  # Track which method was used
                "fetched_full_content": True,  # IMPORTANT: Flag for auto-save
                "full_text": text  # Store the full text for document saving
            }
            
            # Save to cache
            try:
                # Save metadata
                with open(cache_meta_path, 'w', encoding='utf-8') as f:
                    json.dump(formatted_metadata, f, indent=2)
                
                # Save extracted text
                with open(cache_text_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                logger.info(f"Cached arXiv paper {arxiv_id}")
            except Exception as e:
                logger.warning(f"Failed to cache arXiv paper {arxiv_id}: {e}")
            
            # Send complete feedback
            if update_callback and log_queue:
                try:
                    update_callback(log_queue, {
                        "type": "arxiv_fetch_complete",
                        "url": url,
                        "arxiv_id": arxiv_id,
                        "title": metadata["title"],
                        "authors": metadata["authors"],
                        "content_length": len(text),
                        "fetch_method": fetch_method
                    })
                except Exception as e:
                    logger.debug(f"Failed to send complete feedback: {e}")
            
            logger.info(f"Successfully fetched arXiv paper: {metadata['title']} ({len(text)} chars)")
            
            return {
                "text": text,
                "title": metadata["title"],
                "metadata": formatted_metadata,
                "source": "arxiv",
                "fetched_via": f"arxiv_{fetch_method}"
            }
            
        except Exception as e:
            error_msg = f"Error fetching arXiv paper {arxiv_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}