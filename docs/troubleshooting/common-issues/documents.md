# Document Processing Troubleshooting

Quick fixes for document upload and processing issues.

## Upload Issues

### Upload Fails

**Common causes:**
- File too large (>50MB)
- Wrong format (only PDF, DOCX, MD, TXT supported)
- Backend not ready

**Solution:**
```bash
# Check if backend is ready
docker compose logs maestro-backend | grep "Started Successfully"

# For large files, use CLI
./maestro-cli.sh ingest username /path/to/documents
```

### Duplicate Document Error

**Solution:**
```bash
# Force upload despite duplicate
./maestro-cli.sh ingest username /path/to/document --force
```

## Processing Issues

### Documents Stuck in Processing

**Check status:**
```bash
# View processor logs
docker compose logs maestro-doc-processor --tail=50

# Check document consistency
docker exec maestro-backend python cli_document_consistency.py system-status
```

**Fix stuck documents:**
```bash
# Restart processor
docker compose restart maestro-doc-processor

# Clean up orphaned documents
docker exec maestro-backend python cli_document_consistency.py cleanup-all
```

### PDF Processing Failed

**Common issues:**
- Scanned PDFs (no text) - not supported
- Corrupted PDF
- Memory issues

**Solution:**
```bash
# Check if PDF has text
pdftotext problem.pdf - | head

# For memory issues, use CPU mode
echo "FORCE_CPU_MODE=true" >> .env
docker compose restart
```

## Search Issues

### No Search Results

**Check if documents are indexed:**
```bash
# Count documents
docker exec maestro-postgres psql -U maestro_user -d maestro_db -c "SELECT COUNT(*) FROM documents;"

# Count chunks (should be more than documents)
docker exec maestro-postgres psql -U maestro_user -d maestro_db -c "SELECT COUNT(*) FROM document_chunks;"
```

**Solution:**
```bash
# Re-ingest documents
./maestro-cli.sh ingest username /path/to/documents --force-reembed
```

### Poor Search Results

**Adjust search weights in Settings → Research:**

- Increase `main_research_doc_results` for more document results
- Decrease if getting too many irrelevant results

## Document Management

### Cannot Delete Documents

**Solution:**
```bash
# Use web interface to delete
# Or force delete all and re-upload
docker compose down -v
docker compose up -d
```

### Document Groups Not Working

**Add documents to groups during ingestion:**
```bash
./maestro-cli.sh ingest username /path/to/documents --group group_id
```

## Metadata Issues

### Wrong Title or Authors

**Solution:** Metadata is extracted automatically by AI. To fix:

1. Delete document in web interface
2. Re-upload

## Quick Fixes

### Check Processing Status

```bash
# Overall status
docker exec maestro-backend python cli_document_consistency.py system-status

# Specific user
docker exec maestro-backend python cli_document_consistency.py check-user <user_id>
```

### Force Reprocess All Documents

```bash
# Re-ingest with new embeddings
./maestro-cli.sh ingest username /path/to/documents --force-reembed --batch-size 10
```

### Clear All Documents

⚠️ **WARNING: Deletes all documents!**

```bash
docker exec maestro-postgres psql -U maestro_user -d maestro_db -c "TRUNCATE documents CASCADE;"
```

## Common Error Messages

| Error | Solution |
|-------|----------|
| "File type not supported" | Convert to PDF, DOCX, MD, or TXT |
| "Document already exists" | Use `--force` flag with CLI |
| "Processing failed" | Check logs, restart processor |
| "No chunks found" | Document still processing, wait |
| "Embedding generation failed" | Check memory, use CPU mode |

## Still Having Issues?

1. Check logs: `docker compose logs maestro-doc-processor`
2. Enable debug: `LOG_LEVEL=DEBUG` in .env
3. Try complete reset (WARNING: data loss)
4. Use CLI for batch processing