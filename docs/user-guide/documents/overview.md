# Documents Overview

The document management system is the foundation of MAESTRO's research capabilities, allowing you to upload, organize, and search through your document library.

![Document Library](../../assets/images/doc view all docs.png)

## How Document Processing Works

When you upload a document, MAESTRO:

1. **Validates** the file and checks for duplicates (SHA256)
2. **Stores** the original file and creates a database record
3. **Converts** the document to markdown format using:
   - **PDF**: Marker for extraction (GPU-accelerated when available)
   - **Word**: python-docx for .docx/.doc files
   - **Markdown**: Direct processing
4. **Extracts** metadata using LLM (title, authors, abstract)
5. **Chunks** content into overlapping paragraphs (2 per chunk, 1 overlap)
6. **Generates** BGE-M3 embeddings (dense and sparse)
7. **Indexes** for semantic search

## Supported File Formats

- **PDF** (.pdf) - Processed with Marker
- **Microsoft Word** (.docx, .doc) - Extracted with python-docx
- **Markdown** (.md, .markdown) - Direct processing
- **Plain Text** (.txt) - Simple text extraction

## Document Library Features

### Organization

- **Document Groups** - Create collections for projects
- **Metadata** - Automatic extraction of title, authors, abstract
- **Duplicate Detection** - SHA256 hash prevents duplicate uploads

### Search Capabilities

- **Semantic Search** - Find documents by meaning using embeddings
- **Hybrid Search** - Combines dense and sparse embeddings
- **API Endpoint** - `/api/documents/search` for programmatic access

## Processing Status

Documents go through these stages:

- **Uploading** - File being transferred
- **Processing** - Conversion and embedding generation
- **Completed** - Ready for use
- **Failed** - Error occurred (check `processing_error` field)

## Using the Document System

### Web Interface

1. Navigate to the Documents tab
2. Click "Upload Documents" or drag and drop files
3. Monitor processing status
4. Search documents using the search bar

### CLI Upload

Use the maestro-cli.sh script for bulk uploads:

```bash
# Upload documents for a user
./maestro-cli.sh ingest <username> <directory>

# Force re-embedding
./maestro-cli.sh ingest <username> <directory> --force-reembed

# Add to specific group
./maestro-cli.sh ingest <username> <directory> --group <group_id>
```

### Creating Document Groups

Groups help organize documents:

```bash
# Create a group via CLI
./maestro-cli.sh create-group <username> "Group Name"

# List groups
./maestro-cli.sh list-groups
```

## Search and Retrieval

### Search Interface

Enter natural language queries to find relevant documents. The system uses:
- BGE-M3 dense embeddings (1024 dimensions)
- BGE-M3 sparse embeddings (30,000 dimensions)
- Configurable hybrid search weights

### Search Examples

- Conceptual: "papers about machine learning optimization"
- Specific: "CRISPR gene editing techniques"
- Author-based: "research by Smith et al"

## Storage Architecture

Documents are stored in three locations:

1. **PostgreSQL Database** - Metadata and document chunks
2. **File System** - Original files and markdown conversions
   - Raw files: `/app/data/raw_files/{doc_id}_{filename}`
   - Markdown: `/app/data/markdown_files/{doc_id}.md`
3. **PostgreSQL with pgvector** - Embeddings for search

## Processing Performance

- **GPU Available**: Faster PDF processing with Marker
- **CPU Only**: Falls back to CPU (slower but functional)
- **Batch Processing**: Use CLI for efficient bulk uploads
- **Concurrent Uploads**: Multiple files processed in parallel

## Troubleshooting

### Processing Failures

Check the `processing_error` field in the database:
```bash
docker exec maestro-postgres psql -U maestro_user -d maestro_db \
  -c "SELECT id, title, processing_error FROM documents WHERE status = 'failed';"
```

### Re-processing Documents

```bash
# Force re-embedding via CLI
./maestro-cli.sh ingest <username> <directory> --force-reembed
```

### Storage Issues

Monitor disk usage:
```bash
# Check Docker volumes
docker system df

# Check specific paths
du -sh maestro_backend/data/*
```

## Best Practices

1. **File Preparation**
   - Ensure PDFs have extractable text (not scanned images)
   - Keep files under 50MB for optimal processing
   - Use descriptive filenames

2. **Organization**
   - Create groups for different projects
   - Use consistent naming conventions
   - Regular cleanup of unused documents

3. **Performance**
   - Use CLI for bulk uploads
   - Process large batches during off-hours
   - Monitor storage usage

## Next Steps

- [Uploading Documents](uploading.md) - Detailed upload guide
- [Document Groups](document-groups.md) - Organizing collections
- [Search Guide](overview.md#search) - Advanced search techniques
- [CLI Commands](../../getting-started/installation/cli-commands.md) - Bulk operations