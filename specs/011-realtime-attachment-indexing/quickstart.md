# Quickstart: Real-Time Document Indexing

**Feature**: 011-realtime-attachment-indexing  
**Audience**: Developers  
**Time**: 15 minutes

## Overview

This guide shows how to test real-time document indexing locally, monitor tasks, and troubleshoot common issues.

---

## Prerequisites

- Indico development environment running
- Plugin installed and enabled
- PostgreSQL with pgvector extension
- Celery workers running
- Vector search enabled in plugin settings

---

## Quick Test (5 minutes)

### 1. Upload a Test Document

**Via Indico Web UI:**
```
1. Navigate to an event: http://localhost:8000/event/123/
2. Go to Materials → Add new folder
3. Upload a PDF file (<10MB recommended)
4. File is automatically indexed in background
```

**Via API (curl):**
```bash
# Get API token from Indico
TOKEN="your-api-token"

# Upload attachment to event
curl -X POST "http://localhost:8000/api/events/123/attachments/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf" \
  -F "title=Test Document"
```

### 2. Verify Indexing Started

**Check Logs:**
```bash
# Watch plugin logs for indexing activity
tail -f logs/indico.log | grep "indico_assistant"

# Expected output:
# INFO  indico_assistant.plugin - Queued indexing task for attachment 12345
# INFO  indico_assistant.tasks.indexing - Starting indexing for attachment 12345
```

**Check Celery Queue:**
```bash
# If using Flower (Celery monitoring):
open http://localhost:5555/tasks

# Or via Celery CLI:
celery -A indico.core.celery inspect active
```

### 3. Wait for Completion (typically 5-10 seconds)

**Monitor Task Progress:**
```bash
# Watch for completion log
tail -f logs/indico.log | grep "indexed successfully"

# Expected output:
# INFO  indico_assistant.tasks.indexing - Attachment 12345 indexed successfully: 15 chunks in 3.45s
```

### 4. Verify Document is Searchable

**Via Search API:**
```bash
curl -X POST "http://localhost:8000/api/assistant/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "content from your test document",
    "event_id": 123,
    "top_k": 5
  }'

# Expected: Results containing chunks from uploaded document
```

**Via Database Query:**
```sql
-- Connect to PostgreSQL
psql -U indico -d indico

-- Check indexed chunks
SELECT 
    attachment_id,
    chunk_index,
    LEFT(content, 50) as preview,
    content_hash,
    extracted_at
FROM plugin_assistant.extracted_documents
WHERE event_id = 123
ORDER BY extracted_at DESC
LIMIT 10;
```

---

## Manual Task Trigger (for testing)

### Trigger Indexing Manually (bypassing signal)

```python
# In Indico shell (indico shell)
from indico_assistant.tasks.indexing import index_attachment_task

# Queue task for specific attachment
result = index_attachment_task.apply_async(
    args=[12345, 123],  # attachment_id, event_id
    priority=5
)

# Get task ID
print(f"Task ID: {result.id}")

# Wait for result (blocks)
task_result = result.get(timeout=60)
print(task_result)
```

### Check Task Result

```python
# Get task result by ID
from celery.result import AsyncResult

result = AsyncResult('task-id-here')
print(f"Status: {result.state}")
print(f"Result: {result.result}")
```

---

## Monitoring Celery Tasks

### Using Flower (Recommended)

```bash
# Install Flower
pip install flower

# Start Flower
celery -A indico.core.celery flower --port=5555

# Open dashboard
open http://localhost:5555
```

**What to look for:**
- **Active tasks**: Currently running indexing tasks
- **Task history**: Recent completions, failures
- **Worker status**: Number of workers, availability
- **Queue depth**: Pending tasks

### Using Celery CLI

```bash
# List active tasks
celery -A indico.core.celery inspect active

# List scheduled tasks
celery -A indico.core.celery inspect scheduled

# List registered tasks
celery -A indico.core.celery inspect registered | grep index_attachment

# Worker stats
celery -A indico.core.celery inspect stats
```

---

## Troubleshooting

### Issue: Document Not Indexed

**Symptom**: Uploaded file, but no indexing logs appear

**Diagnosis**:
```bash
# 1. Check if vector search is enabled
indico shell
>>> from indico_assistant.plugin import AssistantPlugin
>>> plugin = AssistantPlugin.instance
>>> plugin.settings.get('vector_search_enabled')
True  # Should be True

# 2. Check pgvector availability
>>> from indico_assistant.services.vector_search import check_pgvector_available
>>> check_pgvector_available()
True  # Should be True

# 3. Check if attachment signal connected
>>> from indico.modules.attachments import signals
>>> signals.attachment_created.receivers
[...should include plugin handler...]
```

**Solutions**:
- Enable vector search: `plugin.settings.set('vector_search_enabled', True)`
- Install pgvector: `sudo apt-get install postgresql-14-pgvector`
- Restart plugin: `indico db --plugin assistant upgrade`

---

### Issue: Task Stuck in Queue

**Symptom**: Task appears in queue but never processes

**Diagnosis**:
```bash
# Check if Celery workers are running
ps aux | grep celery

# Check worker logs
tail -f logs/celery.log

# Inspect specific task
celery -A indico.core.celery inspect query_task <task-id>
```

**Solutions**:
- Start workers: `indico celery worker -l info`
- Increase worker concurrency: `indico celery worker -c 4`
- Check for worker errors in logs

---

### Issue: Indexing Fails with Error

**Symptom**: Task completes with `success: false`

**Diagnosis**:
```python
# Get task result
from celery.result import AsyncResult
result = AsyncResult('task-id')
print(result.result)

# Check logs for full traceback
tail -100 logs/indico.log | grep "ERROR.*indexing"
```

**Common Errors**:

**1. "Attachment not found"**
```
Cause: Attachment was deleted before task ran
Solution: No action needed, graceful failure
```

**2. "Extraction failed: corrupted PDF"**
```
Cause: File is corrupted or password-protected
Solution: Re-upload valid file, or mark as unsupported
```

**3. "Embedding service unavailable"**
```
Cause: Network issue or model server down
Solution: Task will auto-retry (3 attempts), check model service logs
```

**4. "Database IntegrityError"**
```
Cause: Duplicate chunk (idempotency - safe to ignore)
Solution: No action needed, this is expected behavior
```

---

### Issue: Slow Indexing (>30s for <10MB)

**Symptom**: Tasks take longer than expected

**Diagnosis**:
```bash
# Check task timing in logs
grep "indexed successfully" logs/indico.log

# Example output:
# Attachment 12345 indexed successfully: 15 chunks in 45.2s

# Check individual step timing
grep "Hash computed" logs/indico.log
grep "Text extracted" logs/indico.log
grep "Embeddings generated" logs/indico.log
```

**Solutions**:
- **Slow embedding**: Check model service latency, consider caching
- **Slow extraction**: Large or complex PDFs may take longer
- **Database slow**: Check PostgreSQL performance, add indexes

---

### Issue: Duplicate Detection Not Working

**Symptom**: Same file indexed multiple times

**Diagnosis**:
```sql
-- Check for duplicate hashes
SELECT 
    content_hash,
    COUNT(*) as count
FROM plugin_assistant.extracted_documents
WHERE event_id = 123
GROUP BY content_hash
HAVING COUNT(*) > 1;
```

**Solutions**:
- Ensure `content_hash` column exists (run migration)
- Check if `force=True` was used (bypasses duplicate detection)
- Verify SHA256 computation is consistent

---

## Testing Different File Types

### PDF Files
```bash
# Small PDF (<10MB)
curl -F "file=@small.pdf" http://localhost:8000/api/events/123/attachments/

# Expected: Indexed in ~3-5 seconds
```

### DOCX Files
```bash
# DOCX document
curl -F "file=@document.docx" http://localhost:8000/api/events/123/attachments/

# Expected: Indexed in ~2-4 seconds (faster than PDF)
```

### Large Files (10-50MB)
```bash
# Large PDF (30MB)
curl -F "file=@large.pdf" http://localhost:8000/api/events/123/attachments/

# Expected: 
# - Logs show "large file" warning
# - Lower priority (priority=9)
# - Indexing may take 15-20 seconds
```

### Unsupported Files (should be ignored)
```bash
# Image file (not supported)
curl -F "file=@image.jpg" http://localhost:8000/api/events/123/attachments/

# Expected:
# - No indexing task queued
# - Log: "Skipping unsupported format: image.jpg"
# - File still stored in Indico normally
```

### Oversized Files (>50MB, should be rejected)
```bash
# Very large file
curl -F "file=@huge.pdf" http://localhost:8000/api/events/123/attachments/

# Expected:
# - No indexing task queued
# - Log: "File too large: 52428800 bytes exceeds 50MB limit"
# - File still stored in Indico normally
```

---

## Performance Benchmarking

### Measure Signal Handler Performance

```python
# In indico shell
import time
from unittest.mock import Mock

plugin = AssistantPlugin.instance

# Mock attachment
attachment = Mock()
attachment.id = 12345
attachment.file.size = 5 * 1024 * 1024  # 5MB
attachment.file.filename = "test.pdf"
attachment.file.content_type = "application/pdf"
attachment.folder.event.id = 123

# Measure handler time
start = time.time()
plugin._on_attachment_created(sender=None, attachment=attachment)
elapsed_ms = (time.time() - start) * 1000

print(f"Signal handler took: {elapsed_ms:.2f}ms")
# Target: <100ms
```

### Measure Task Performance

```python
# In indico shell
import time
from indico_assistant.tasks.indexing import index_attachment_task

start = time.time()
result = index_attachment_task.apply(args=[12345, 123])
elapsed_s = time.time() - start

print(f"Task completed in: {elapsed_s:.2f}s")
print(f"Task result: {result}")
# Target: <30s for <10MB files
```

---

## Configuration Tips

### Adjust File Size Limits

```python
# In indico shell
from indico_assistant.plugin import AssistantPlugin

plugin = AssistantPlugin.instance

# Change max file size (default: 50MB)
plugin.settings.set('max_file_size_mb', 100)
```

### Adjust Celery Rate Limits

```python
# In tasks/indexing.py
@celery.task(
    bind=True,
    max_retries=3,
    rate_limit='20/m'  # Change from 10/m to 20/m
)
```

### Increase Worker Concurrency

```bash
# Start with more workers
indico celery worker -c 8  # 8 concurrent workers
```

---

## Next Steps

1. ✅ Test basic upload and indexing
2. ✅ Monitor tasks via Flower
3. ✅ Test different file types
4. ⏭️ Write integration tests
5. ⏭️ Set up production monitoring
6. ⏭️ Configure alerts for failed tasks

---

## Useful Commands Reference

```bash
# Plugin status
indico db --plugin assistant current

# Run migrations
indico db --plugin assistant upgrade

# Start Celery worker
indico celery worker -l info

# Start Flower monitoring
celery -A indico.core.celery flower

# View plugin settings
indico shell -c "from indico_assistant.plugin import AssistantPlugin; print(AssistantPlugin.instance.settings.get_all())"

# Clear Celery queue (dev only!)
celery -A indico.core.celery purge

# Restart Celery workers
pkill -f "celery worker" && indico celery worker -l info &
```

---

## Support

- **Logs**: `logs/indico.log` and `logs/celery.log`
- **Documentation**: [VECTOR_SEARCH_SETUP.md](../../../docs/VECTOR_SEARCH_SETUP.md)
- **Issues**: Check `extracted_documents` table for indexing status
- **Performance**: Use Flower dashboard for task metrics