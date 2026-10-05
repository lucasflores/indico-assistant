# Contract: changes to the public chat API

The API stays as specs 004, 019 and 020 define it. Changes:

1. **`GET /api/assistant/chat/jobs/<id>`, when done:** `metadata` gains `citations: [{attachment_id, filename, page,
   url}]`, where `url` opens the file at `#page=N`. `data_sources` is unchanged.
2. **`GET /api/assistant/sessions/<id>`:** each answer's `metadata` also carries `route` (`fast:chat`,
   `fast:out_of_scope` or `agent`, plus `tools`) and `touched` (data-model). These are already returned today; only
   the values change.
3. **`POST /api/assistant/chat/uploads`:** PowerPoint files are now also indexed after they're attached. Uploading
   accepted them already.
4. **`POST /api/assistant/search`** (the old search endpoint) and admin `/search/status` are removed in story 2
   (FR-027). The health endpoint (`/api/assistant/health`) reports document status counts (queued, reading, ready,
   no text, failed, unsupported) instead (constitution IV).

No other endpoint changes. The acceptance suite talks to the assistant only through this API. It also uses:
- the admin trace endpoint (`/admin/turns/by-answer/<uuid>`) for `no_lookup` checks and each turn's cost;
- database reads, which test Indico and don't talk to the assistant: `state` checks, and waiting for documents to
  be indexed (`wait_ready`).
