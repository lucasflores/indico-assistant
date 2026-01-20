# Quickstart: README Update Validation Checklist

**Phase**: 1 (Design)  
**Date**: January 20, 2026

## Purpose

This quickstart provides a step-by-step validation checklist for verifying README accuracy against the codebase using comparison verification methodology.

## Pre-Validation Setup

**Time**: 2 minutes

1. **Checkout feature branch**:
   ```bash
   git checkout 014-readme-framework-review
   ```

2. **Navigate to repository root**:
   ```bash
   cd /Users/lucasflores/dev2/indico/plugins_lucas/indico_assistant_plugin
   ```

3. **Have files ready for comparison**:
   - README.md (target file)
   - indico_assistant/default_settings.py
   - indico_assistant/cli.py
   - indico_assistant/controllers/
   - pyproject.toml
   - indico_assistant/version.py

## Validation Steps

### Step 1: Version Accuracy (2 minutes)

**Objective**: Verify version badge matches actual version

- [ ] Open `indico_assistant/version.py`
- [ ] Note version number (currently 0.1.0)
- [ ] Verify README header shows matching version badge
- [ ] Verify "Last Updated" date is current

**Command**:
```bash
grep "version" indico_assistant/version.py
```

**Expected**: `__version__ = "0.1.0"`

---

### Step 2: Dependencies Accuracy (3 minutes)

**Objective**: Verify all listed dependencies match pyproject.toml

- [ ] Open `pyproject.toml` [dependencies] section
- [ ] Compare each dependency in README against pyproject.toml
- [ ] Verify version constraints match
- [ ] Ensure no missing dependencies

**Command**:
```bash
grep -A 20 "dependencies = \[" pyproject.toml
```

**Checklist**:
- [ ] indico>=3.3
- [ ] instructor>=1.0.0
- [ ] openai>=1.0.0
- [ ] ollama>=0.3.0
- [ ] langfuse>=2.0.0
- [ ] sentence-transformers>=2.2.0
- [ ] PyPDF2>=3.0.0
- [ ] python-docx>=0.8.11
- [ ] pgvector>=0.2.0
- [ ] PyJWT>=2.8.0

---

### Step 3: Configuration Settings Accuracy (5 minutes)

**Objective**: Verify all settings match default_settings.py

- [ ] Open `indico_assistant/default_settings.py`
- [ ] Compare Global Settings table in README
- [ ] Compare Chat Widget Settings table
- [ ] Verify default values match exactly

**Command**:
```bash
grep "DEFAULT_SETTINGS\|EVENT_SETTINGS_DEFAULTS" -A 50 indico_assistant/default_settings.py
```

**Verification Points**:
- [ ] Setting names spelled correctly
- [ ] Default values accurate
- [ ] Data types correct (boolean/string/integer)
- [ ] No missing settings
- [ ] No deprecated settings listed

---

### Step 4: API Endpoints Accuracy (5 minutes)

**Objective**: Verify all documented endpoints exist in controllers

- [ ] List all endpoints in README API section
- [ ] Check each endpoint against controller files

**Commands**:
```bash
# Health endpoint
grep "@blueprint.route.*health" indico_assistant/controllers/health.py

# Chat endpoints
grep "@blueprint.route" indico_assistant/controllers/chat.py

# Search endpoint
grep "@blueprint.route.*search" indico_assistant/controllers/search.py

# Feedback endpoint
grep "@blueprint.route.*feedback" indico_assistant/controllers/feedback.py
```

**Endpoint Checklist**:
- [ ] GET /api/assistant/health
- [ ] POST /api/assistant/chat/sessions
- [ ] GET /api/assistant/chat/sessions
- [ ] POST /api/assistant/chat/sessions/<id>/messages
- [ ] GET /api/assistant/chat/sessions/<id>/messages
- [ ] POST /api/assistant/feedback
- [ ] POST /api/assistant/search

---

### Step 5: CLI Commands Accuracy (3 minutes)

**Objective**: Verify all documented CLI commands exist

- [ ] Open `indico_assistant/cli.py`
- [ ] Compare each command in README against CLI definitions

**Command**:
```bash
grep "@click.command\|@cli.command" -A 2 indico_assistant/cli.py
```

**Command Checklist**:
- [ ] `indico assistant health`
- [ ] `indico assistant config`
- [ ] `indico assistant config --show-secrets`
- [ ] `indico assistant test-llm`
- [ ] `indico assistant index-documents`

---

### Step 6: Feature Descriptions Accuracy (10 minutes)

**Objective**: Verify feature summaries match spec descriptions

- [ ] For each of 13 features, compare README summary against spec file
- [ ] Ensure capabilities described are actually implemented

**Command Pattern** (repeat for each spec):
```bash
head -n 20 specs/001-plugin-foundation/spec.md
head -n 20 specs/002-llm-service-layer/spec.md
# ... through 013
```

**Feature Checklist**:
- [ ] 001 - Plugin Foundation
- [ ] 002 - LLM Service Layer  
- [ ] 003 - NL2SQL Pipeline
- [ ] 004 - Chat REST API
- [ ] 005 - Langfuse Observability
- [ ] 006 - Vector Search RAG
- [ ] 007 - TDD Gap Analysis
- [ ] 008 - Chat Widget
- [ ] 009 - Chat Widget Styling
- [ ] 010 - Chat Pipeline Integration
- [ ] 011 - Realtime Attachment Indexing
- [ ] 012 - Conversation History
- [ ] 013 - NL2SQL Prompt Optimization

---

### Step 7: External Documentation Links (2 minutes)

**Objective**: Verify all linked docs exist and are current

- [ ] Check each linked file exists
- [ ] Verify link paths are correct (relative)

**Commands**:
```bash
ls -l docs/DEPLOYMENT.md
ls -l docs/ACCESSIBILITY.md
ls -l docs/LANGFUSE_SETUP.md
ls -l docs/VECTOR_SEARCH_SETUP.md
```

**Link Checklist**:
- [ ] DEPLOYMENT.md exists
- [ ] ACCESSIBILITY.md exists
- [ ] LANGFUSE_SETUP.md exists
- [ ] VECTOR_SEARCH_SETUP.md exists

---

### Step 8: Architecture Section Accuracy (3 minutes)

**Objective**: Verify directory structure matches actual layout

- [ ] Compare README architecture tree against actual file structure
- [ ] Verify module descriptions are accurate

**Command**:
```bash
ls -la indico_assistant/
ls -la docs/
ls pyproject.toml README.md
```

**Structure Checklist**:
- [ ] indico_assistant/ directory structure accurate
- [ ] Key files mentioned exist (plugin.py, blueprint.py, cli.py, etc.)
- [ ] Module purposes correctly described

---

### Step 9: Table of Contents Navigation (2 minutes)

**Objective**: Verify all TOC links work

- [ ] Click each TOC link in preview/browser
- [ ] Verify anchor navigation works
- [ ] Ensure no broken internal links

**Manual Test**: Open README in GitHub preview or IDE markdown viewer and test all TOC links

---

### Step 10: Code Examples Validity (5 minutes)

**Objective**: Verify usage examples are syntactically correct and represent actual usage

- [ ] Review Python code examples for syntax errors
- [ ] Verify bash commands are accurate
- [ ] Check import statements are correct

**No automated test** - manual review of:
- [ ] NL2SQL pipeline example imports and method calls
- [ ] CLI command examples match actual commands
- [ ] API curl examples use correct endpoints

---

## Validation Summary

**Total Time**: ~40 minutes for complete validation

**Pass Criteria**:
- All checkboxes above marked ✓
- Zero discrepancies found between README and code
- All links functional
- All code examples valid

**If Failures Found**:
1. Document discrepancy (what vs. where)
2. Update README to match code (code is source of truth)
3. Re-run relevant validation step
4. Mark checkbox when resolved

## Quick Re-Validation

After README updates, re-run abbreviated checklist:

**Quick Check** (5 minutes):
- [ ] Version matches version.py
- [ ] No typos in recently edited sections
- [ ] New links are valid
- [ ] Code examples have no syntax errors

## Sign-Off

**Validated by**: _____________  
**Date**: _____________  
**All checks passed**: Yes / No  
**Notes**: _____________
