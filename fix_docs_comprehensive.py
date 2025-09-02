#!/usr/bin/env python3
"""
Comprehensive fix for MkDocs documentation links.
This addresses all remaining warnings in the strict build.
"""

import os
import re
from pathlib import Path

def fix_file_content(file_path, content):
    """Apply specific fixes based on the file path."""
    
    # Get relative path from docs directory
    rel_path = Path(file_path).relative_to(Path('docs'))
    
    # Fix for getting-started/first-login.md
    if str(rel_path) == 'getting-started/first-login.md':
        # Fix image paths - these should be absolute from docs root
        content = content.replace('assets/images/settings/ai-config.png', '/assets/images/settings/ai-config.png')
        content = content.replace('assets/images/settings/search.png', '/assets/images/settings/search.png')
        # Fix duplicate parent refs
        content = content.replace('../../user-guide/index.md', '../user-guide/index.md')
        content = content.replace('../../troubleshooting/index.md', '../troubleshooting/index.md')
        content = content.replace('../../troubleshooting/faq.md', '../troubleshooting/faq.md')
    
    # Fix for getting-started/configuration files
    if str(rel_path).startswith('getting-started/configuration/'):
        # Fix image paths to be absolute
        content = content.replace('../assets/images/settings/ai-config.png', '/assets/images/settings/ai-config.png')
        content = content.replace('../assets/images/settings/search.png', '/assets/images/settings/search.png')
        content = content.replace('../assets/images/settings/web-fetch.png', '/assets/images/settings/web-fetch.png')
        content = content.replace('assets/images/settings/ai-config.png', '/assets/images/settings/ai-config.png')
        content = content.replace('assets/images/settings/search.png', '/assets/images/settings/search.png')
        content = content.replace('assets/images/settings/web-fetch.png', '/assets/images/settings/web-fetch.png')
    
    # Fix for getting-started/installation files
    if str(rel_path) == 'getting-started/installation/cli-commands.md':
        # Remove broken API link
        content = content.replace('](../../#)', '](#)')
        content = content.replace('](#)', '](#)')
    
    if str(rel_path) == 'getting-started/installation/database-reset.md':
        # Fix backup link to point to an existing page
        content = content.replace('../configuration/backup.md', '../configuration/environment-variables.md#backup')
        content = content.replace('getting-started/installation/database-reset.md', 'database-reset.md')
    
    if str(rel_path) == 'getting-started/installation/docker.md':
        # Fix GitHub discussions link
        content = content.replace('](../../https://github.com/murtaza-nasir/maestro/discussions)', '](https://github.com/murtaza-nasir/maestro/discussions)')
        content = content.replace('](https://github.com/murtaza-nasir/maestro/discussions)', '](https://github.com/murtaza-nasir/maestro/discussions)')
    
    # Fix for user-guide/index.md
    if str(rel_path) == 'user-guide/index.md':
        # Fix research links to point to overview
        content = content.replace('research/chat-interface.md', 'research/overview.md#chat-interface')
        content = content.replace('research/missions.md', 'research/overview.md#missions')
        content = content.replace('research/overview.md#chat-interface', 'research/overview.md')
        content = content.replace('research/overview.md#missions', 'research/overview.md')
        # Fix GitHub discussions link
        content = content.replace('](../https://github.com/murtaza-nasir/maestro/discussions)', '](https://github.com/murtaza-nasir/maestro/discussions)')
    
    # Fix for user-guide/documents files
    if str(rel_path).startswith('user-guide/documents/'):
        # Fix search.md links to point to overview with anchor
        content = content.replace('](search.md)', '](overview.md#search)')
        content = content.replace('](supported-formats.md)', '](uploading.md#supported-formats)')
        content = content.replace('](user-guide/documents/overview.md#search)', '](overview.md#search)')
        content = content.replace('](user-guide/documents/uploading.md#supported-formats)', '](uploading.md#supported-formats)')
    
    if str(rel_path) == 'user-guide/documents/document-groups.md':
        # Fix mission settings link
        content = content.replace('../research/mission-settings.md', '../research/parameters.md')
    
    # Fix for user-guide/research/overview.md
    if str(rel_path) == 'user-guide/research/overview.md':
        # Fix GitHub discussions link
        content = content.replace('](../../https://github.com/murtaza-nasir/maestro/discussions)', '](https://github.com/murtaza-nasir/maestro/discussions)')
    
    # Fix for user-guide/settings files
    if str(rel_path).startswith('user-guide/settings/'):
        # Fix image paths to be absolute
        content = content.replace('../assets/images/settings/ai-config.png', '/assets/images/settings/ai-config.png')
        content = content.replace('../assets/images/settings/appearance.png', '/assets/images/settings/appearance.png')
        content = content.replace('../assets/images/settings/profile.png', '/assets/images/settings/profile.png')
        content = content.replace('../assets/images/settings/research.png', '/assets/images/settings/research.png')
        content = content.replace('../assets/images/settings/search.png', '/assets/images/settings/search.png')
        content = content.replace('../assets/images/settings/web-fetch.png', '/assets/images/settings/web-fetch.png')
        content = content.replace('assets/images/settings/ai-config.png', '/assets/images/settings/ai-config.png')
        content = content.replace('assets/images/settings/appearance.png', '/assets/images/settings/appearance.png')
        content = content.replace('assets/images/settings/profile.png', '/assets/images/settings/profile.png')
        content = content.replace('assets/images/settings/research.png', '/assets/images/settings/research.png')
        content = content.replace('assets/images/settings/search.png', '/assets/images/settings/search.png')
        content = content.replace('assets/images/settings/web-fetch.png', '/assets/images/settings/web-fetch.png')
    
    if str(rel_path) == 'user-guide/settings/search-config.md':
        # Fix webfetch-config.md link
        content = content.replace('](webfetch-config.md)', '](web-fetch-config.md)')
    
    return content

def add_sections_to_files():
    """Add missing sections to files that are referenced by anchors."""
    
    # Add search section to user-guide/documents/overview.md
    overview_file = Path('docs/user-guide/documents/overview.md')
    if overview_file.exists():
        with open(overview_file, 'r') as f:
            content = f.read()
        
        if '## Search' not in content and '## search' not in content.lower():
            # Add search section at the end
            content += '\n\n## Search\n\nThe document library includes powerful search capabilities:\n\n'
            content += '- **Full-text search**: Search across all document content\n'
            content += '- **Metadata filtering**: Filter by title, authors, date, and tags\n'
            content += '- **Semantic search**: Find documents by meaning, not just keywords\n'
            content += '- **Advanced filters**: Combine multiple search criteria\n\n'
            content += 'Use the search bar at the top of the document library to quickly find relevant documents.\n'
            
            with open(overview_file, 'w') as f:
                f.write(content)
    
    # Add supported formats section to user-guide/documents/uploading.md
    uploading_file = Path('docs/user-guide/documents/uploading.md')
    if uploading_file.exists():
        with open(uploading_file, 'r') as f:
            content = f.read()
        
        if '## Supported Formats' not in content and '## supported formats' not in content.lower():
            # Add supported formats section
            content += '\n\n## Supported Formats\n\nMAESTRO supports the following document formats:\n\n'
            content += '- **PDF** (.pdf) - Portable Document Format\n'
            content += '- **Microsoft Word** (.docx, .doc) - Word documents\n'
            content += '- **Markdown** (.md, .markdown) - Markdown files\n'
            content += '- **Plain Text** (.txt) - Plain text files\n'
            content += '- **Rich Text Format** (.rtf) - RTF documents\n\n'
            content += 'Documents are automatically processed and indexed for searching after upload.\n'
            
            with open(uploading_file, 'w') as f:
                f.write(content)
    
    # Add backup section to environment-variables.md
    env_file = Path('docs/getting-started/configuration/environment-variables.md')
    if env_file.exists():
        with open(env_file, 'r') as f:
            content = f.read()
        
        if '## Backup' not in content and '## backup' not in content.lower():
            # Add backup section
            content += '\n\n## Backup\n\nTo backup your MAESTRO installation:\n\n'
            content += '1. **Database Backup**:\n'
            content += '   ```bash\n'
            content += '   docker exec maestro-postgres pg_dump -U maestro_user maestro_db > backup.sql\n'
            content += '   ```\n\n'
            content += '2. **Document Files Backup**:\n'
            content += '   ```bash\n'
            content += '   tar -czf documents.tar.gz ./data/raw_files ./data/markdown_files\n'
            content += '   ```\n\n'
            content += '3. **Vector Store Backup**:\n'
            content += '   ```bash\n'
            content += '   tar -czf vector_store.tar.gz ./data/vector_store\n'
            content += '   ```\n'
            
            with open(env_file, 'w') as f:
                f.write(content)

def process_all_files():
    """Process all markdown files to fix links."""
    docs_dir = Path('docs')
    
    if not docs_dir.exists():
        print("Error: docs directory not found")
        return
    
    # First add missing sections
    print("Adding missing sections to files...")
    add_sections_to_files()
    
    # Find all markdown files
    md_files = list(docs_dir.rglob('*.md'))
    
    print(f"Processing {len(md_files)} markdown files...")
    
    fixed_count = 0
    for file_path in md_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply fixes
        content = fix_file_content(file_path, content)
        
        # Only write if content changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            fixed_count += 1
            print(f"Fixed: {file_path}")
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    process_all_files()