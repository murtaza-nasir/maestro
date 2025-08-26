#!/usr/bin/env python3
"""
Test script for the markdown_to_docx converter.
This script tests the improved markdown to DOCX conversion functionality.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the Python path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_researcher.ui.file_converters import markdown_to_docx

def main():
    """Test the markdown_to_docx function with various markdown elements."""
    # Create a test markdown string with various elements
    test_markdown = """# Test Document

## Introduction

This is a test document to verify the **bold text** and *italic text* formatting.

### Numbered Lists

1. First item
2. Second item with **bold text**
3. Third item with *italic text*
4. Fourth item with [reference][1]

### Bullet Lists

- Item one
- Item two with **bold**
- Item three with *italic*

## References Section

1. Sepideh Ebrahimi, Esraa Abdelhalim, Khaled Hassanein, Milena Head. (2024). Reducing the incidence of biased algorithmic decisions through feature importance transparency: an empirical study. *European Journal of Information Systems*.

## Code Example

```python
def hello_world():
    print("Hello, World!")
```

5. **Continuous Learning from Empirical Cases and Contexts:** Continuously study and learn from empirical examples of ADM implementation in resource allocation, both successes and failures, across diverse institutional settings. Understanding the complex interplay of technical, institutional, professional, and ethical factors in specific contexts informs best practices and helps identify mechanisms that either perpetuate or challenge existing inequalities [4][6].

Addressing the challenges of algorithmic decision systems in resource allocation requires a holistic approach that considers the intricate relationships between technology and its social, institutional, and ethical context. Future research should continue to explore these dynamics through interdisciplinary and empirical studies, focusing on specific mechanisms of interaction and developing practical strategies for designing and governing ADM systems that promote equitable and just outcomes.
"""

    # Convert the markdown to DOCX
    docx_bytes = markdown_to_docx(test_markdown)
    
    # Save the DOCX file
    output_file = "test_output.docx"
    with open(output_file, "wb") as f:
        f.write(docx_bytes)
    
    print(f"DOCX file created: {os.path.abspath(output_file)}")
    print("Please open this file to verify the formatting.")

if __name__ == "__main__":
    main()
