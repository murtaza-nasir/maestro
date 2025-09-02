#!/usr/bin/env python3
"""
Fix broken links in MkDocs documentation.
This script addresses image links and internal document references.
"""

import os
import re
from pathlib import Path

def fix_image_links(content, file_path):
    """Fix broken image links by removing incorrect relative paths."""
    fixes = [
        # Fix image paths that use incorrect relative paths
        (r'\.\./assets/images/settings/', 'assets/images/settings/'),
        (r'\.\./\.\./assets/images/settings/', 'assets/images/settings/'),
        (r'\.\./\.\./images/', 'images/'),
        (r'\.\./images/', 'images/'),
        
        # Fix user-guide image paths
        (r'\.\./\.\./images/user-guide/', 'images/user-guide/'),
        
        # Fix troubleshooting image paths
        (r'\.\./\.\./assets/images/troubleshooting/', 'assets/images/troubleshooting/'),
    ]
    
    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content)
    
    return content

def fix_internal_links(content, file_path):
    """Fix broken internal document links."""
    fixes = [
        # Remove duplicate parent directory references
        (r'\.\./\.\./user-guide/index\.md', '../user-guide/index.md'),
        (r'\.\./\.\./troubleshooting/index\.md', '../troubleshooting/index.md'),
        (r'\.\./\.\./troubleshooting/faq\.md', '../troubleshooting/faq.md'),
        
        # Fix missing pages that don't exist
        ('troubleshooting/common-issues/index.md', 'troubleshooting/common-issues/installation.md'),
        ('common-issues/index.md', 'common-issues/installation.md'),
        ('user-guide/research/chat-interface.md', 'user-guide/research/overview.md'),
        ('user-guide/research/missions.md', 'user-guide/research/overview.md'),
        ('user-guide/research/mission-settings.md', 'user-guide/research/parameters.md'),
        ('user-guide/documents/search.md', 'user-guide/documents/overview.md#search'),
        ('user-guide/documents/supported-formats.md', 'user-guide/documents/uploading.md#supported-formats'),
        ('user-guide/settings/webfetch-config.md', 'user-guide/settings/web-fetch-config.md'),
        
        # Fix links to non-existent pages
        ('deployment/kubernetes/helm-chart.md', 'deployment/local-llms.md'),
        ('community/discussions.md', 'https://github.com/murtaza-nasir/maestro/discussions'),
        ('api/index.md', '#'),
        ('getting-started/configuration/backup.md', 'getting-started/installation/database-reset.md'),
        ('troubleshooting/performance.md', 'troubleshooting/common-issues/installation.md'),
    ]
    
    for pattern, replacement in fixes:
        content = content.replace(pattern, replacement)
    
    return content

def remove_broken_image_references(content):
    """Comment out image references that don't have corresponding files."""
    # Images that don't exist - comment them out instead of removing
    missing_images = [
        '01-document-library.png',
        'doc view all docs.png',
        'doc view document groups.png',
        'doc view filters.png',
        'doc view drag and drop upload.png',
        'Research view.png',
        'Research view-plan outline.png',
        'Resarch view notes.png',
        'Research view draft.png',
        'research view settings.png',
        'writing view chat.png',
        'writing view search settings.png',
        'writing view additional instructions.png',
        'writing view references in chat.png',
        'writing view fomrulas and tables in latex and markdown.png',
        'writing view editor and preview (is available to assistant in context, not for editing).png',
        'ai-config-model-selection.png',
    ]
    
    for img in missing_images:
        # Comment out the image reference instead of removing it
        pattern = rf'!\[([^\]]*)\]\([^)]*{re.escape(img)}[^)]*\)'
        replacement = rf'<!-- Image not available: \1 ({img}) -->'
        content = re.sub(pattern, replacement, content)
    
    return content

def process_file(file_path):
    """Process a single markdown file to fix links."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply fixes
    content = fix_image_links(content, file_path)
    content = fix_internal_links(content, file_path)
    content = remove_broken_image_references(content)
    
    # Only write if content changed
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    """Main function to process all markdown files."""
    docs_dir = Path('docs')
    
    if not docs_dir.exists():
        print("Error: docs directory not found")
        return
    
    # Find all markdown files
    md_files = list(docs_dir.rglob('*.md'))
    
    print(f"Found {len(md_files)} markdown files")
    
    fixed_count = 0
    for file_path in md_files:
        if process_file(file_path):
            fixed_count += 1
            print(f"Fixed: {file_path}")
    
    print(f"\nFixed {fixed_count} files")
    
    # Create placeholder content for missing images directory structure
    print("\nCreating placeholder directories for missing images...")
    
    # Ensure all required image directories exist
    image_dirs = [
        'docs/images/user-guide',
        'docs/assets/images/troubleshooting',
    ]
    
    for dir_path in image_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"Created: {dir_path}")

if __name__ == "__main__":
    main()