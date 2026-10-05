# Documents

The assistant reads every file attached to an event: it can list an event's documents, read a document's start,
pages or a section, and search them, and it cites each page it used (spec 025). This page is for whoever runs the
plugin.

## What is read

- **Formats:** PDF, Word (`.docx`), PowerPoint (`.pptx`, one page per slide, speaker notes included), text and
  Markdown. Other files get the status "unsupported". Files of 50 MB or more are not read.
- **Structure:** pages (or slides) and sections. Sections come from the PDF's outline, Word's heading styles, slide
  titles or Markdown headings. Without those, numbered headings are found in the text ("4.4.1 Fit Quality Measure",
  or "Chapter 4" over its title); contents pages and numbered list items are left out.
- **Text:** PDF text is NFKC-normalised, so ligatures read as letters ("different", not "dierent"). A scan with no
  text layer gets the status "no text": there is no OCR.

## When it is read

- An uploaded or changed attachment is marked **queued** in the upload's own transaction, and read by a worker on the
  `assistant_bulk` queue once it commits: **reading**, then **ready** (or **no text**, **failed**, **unsupported**).
  The assistant tells users plainly when a document is still being read or can't be.
- Deleting an attachment or its folder deletes its document in the same transaction. A nightly task removes the
  documents of attachments deleted while the plugin was off, and fails reads whose worker died.
- `indico assistant sync-documents` queues every attachment whose current file hasn't been read; `--force` reads
  them all again; `--event N` reads one event's attachments right away, in the command itself.

## Search

Passages are ranked twice in one SQL statement, by keyword (PostgreSQL full text, `simple` configuration) and by
meaning (pgvector), and the two rankings are fused by reciprocal rank. Each passage is indexed with its document's
title and section. Only documents whose attachment the user can open are searched, as Indico itself decides
(`Attachment.can_access`, checked as that user).

- **pgvector** is optional. Without the `vector` extension, search is keyword-only. Install it before migration 012
  to get the embedding column: `CREATE EXTENSION vector;` as a superuser in Indico's database.
- **The embedding model** (`BAAI/bge-small-en-v1.5`, 384 dimensions) runs in the worker. Download it once into the
  worker's Hugging Face cache; the user-guide search (spec 022) uses the same model.
- **No approximate index:** an exact scan is fast for the thousands of chunks a site holds. Add an HNSW index on
  `plugin_assistant.document_chunks.embedding` past about 100,000 chunks.

## Settings and health

- **Admin → Plugins → Assistant:** "Vector search enabled" switches reading documents on or off; the turn's limits
  (requests, tool calls, cost and time per answer) bound how much reading one answer may do.
- `GET /api/assistant/health` reports how many documents are in each status, and whether search has vectors.

## Tables

`plugin_assistant.documents` (one row per attachment: file version, status, error, pages, outline) and
`plugin_assistant.document_chunks` (page, offset, section, text, keyword index, embedding). The read-only NL2SQL role
has no access to either: documents are read only through the assistant's own tools.
