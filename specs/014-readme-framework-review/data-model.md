# Data Model: README Structure

**Phase**: 1 (Design)  
**Date**: January 20, 2026

## Overview

This document defines the structural model for the README.md file, including sections, subsections, content types, and relationships.

## README Document Entity

**Purpose**: Single markdown file serving as primary entry point for all stakeholders

**Attributes**:
- Version: 0.1.0
- Last Updated: January 20, 2026
- Format: GitHub-flavored Markdown
- Target Length: 300-500 lines
- Reading Time: ~10-15 minutes for full read, <2 minutes for navigation

## Section Entities

### 1. Header Section

**Location**: Top of file  
**Content**:
- Title: "# Indico Assistant Plugin"
- Version badge: "Version 0.1.0"
- Last updated date
- One-sentence tagline
- **Relationships**: None (standalone)

### 2. Table of Contents

**Location**: After header, before Features  
**Content**:
- Markdown anchor links to all major sections
- Two-level hierarchy (section + key subsections)
- Auto-scroll navigation
- **Relationships**: Links to all Section entities

### 3. Features Section

**Location**: First content section  
**Content**:
- Bullet list of 13 features
- Each feature: 2-3 sentence summary
- Links to detailed docs where applicable
- Grouped logically (Core, Integration, Developer Tools)
- **Relationships**: 
  - Contains 13 Feature Summary entities
  - Links to External Documentation entities

### 4. Requirements Section

**Location**: After Features  
**Content**:
- Indico version requirement (3.3+)
- Python version requirement (3.11+)
- PostgreSQL (implicit via Indico)
- **Relationships**: Validates against Technical Context in plan.md

### 5. Installation Section

**Location**: After Requirements  
**Content**:
- pip install command
- Development installation steps
- Virtual environment creation
- **Relationships**: References pyproject.toml dependencies

### 6. Configuration Section

**Location**: After Installation  
**Content**:
- 3 subsections: Global Settings, Chat Widget Settings, Per-Event Settings
- Table format with setting name, description, default
- Navigation instructions (Admin → Plugins → Assistant)
- **Relationships**: 
  - Contains 3 Configuration Subsection entities
  - Validates against default_settings.py

#### 6.1 Global Settings Subsection

**Content**:
- Enable Assistant (boolean, default: True)
- LLM Provider (enum, default: Ollama)
- LLM Model (string, default: llama3.2)
- LLM Base URL (string, default: http://localhost:11434)
- API Key (string, default: blank)
- Timeout (integer, default: 30)
- Max Tokens (integer, default: 2048)

#### 6.2 Chat Widget Settings Subsection

**Content**:
- Chat Widget Enabled (boolean, default: False)
- Chainlit Server URL (string, default: http://localhost:8000)
- Chainlit Auth Secret (string, default: blank)
- Widget behavior notes (JWT, theme, session)

#### 6.3 Per-Event Settings Subsection

**Content**:
- Assistant Enabled per event (boolean, inherits global)
- Custom System Prompt (text, optional override)
- Allowed Tables (multi-select, restricts data access)

#### 6.4 Observability Settings Subsection (conditional)

**Content** (if Langfuse settings exist in default_settings.py):
- Langfuse Enabled (boolean, default: False)
- Langfuse Public Key (string)
- Langfuse Secret Key (string)
- Langfuse Host (string, default: https://cloud.langfuse.com)

#### 6.5 Vector Search Settings Subsection (conditional)

**Content** (if vector search settings exist in default_settings.py):
- Vector Search Enabled (boolean, default: False)
- Embedding Model (string, default: all-MiniLM-L6-v2)
- Chunk Size (integer, default: 500)
- Chunk Overlap (integer, default: 50)
- **Relationships**: Links to DEPLOYMENT.md

#### 6.3 Per-Event Settings Subsection

**Content**:
- Enable/Disable per event
- Custom System Prompt
- Allowed Tables
- Navigation path for event managers

### 7. API Endpoints Section

**Location**: After Configuration  
**Content**:
- Subsections for each endpoint group (Health, Chat, Search, Feedback)
- Request method + path
- Request/response examples
- Status values and meanings
- **Relationships**: 
  - Contains 7 API Endpoint entities
  - Validates against controllers/*.py

### 8. NL2SQL Pipeline Section

**Location**: After API Endpoints  
**Content**:
- Usage example (Python code)
- Supported question types table
- Security features list
- Pipeline result structure
- **Relationships**: 
  - References spec 003
  - Validates against services/nl2sql/*.py

### 9. CLI Commands Section

**Location**: After Usage examples  
**Content**:
- Command list with examples
- Output format descriptions
- **Relationships**: Validates against cli.py

### 10. Development Section

**Location**: After CLI  
**Content**:
- 3 subsections: Setup, Testing, Code Quality
- Step-by-step instructions
- Command examples with expected output
- **Relationships**: 
  - Contains 3 Development Subsection entities
  - References pyproject.toml dev dependencies

#### 10.1 Setup Subsection

**Content**:
- Virtual environment creation
- Development installation command
- Dependency installation

#### 10.2 Testing Subsection

**Content**:
- pytest commands (all, coverage, specific types)
- Coverage report generation
- Test organization (unit, integration, contract)

#### 10.3 Code Quality Subsection

**Content**:
- ruff check command
- black format command
- mypy type checking command

### 11. Architecture Section

**Location**: After Development  
**Content**:
- Directory tree with module descriptions
- Brief explanation of each major module
- **Relationships**: Validates against actual file structure

### 12. Security Section

**Location**: After Architecture  
**Content**:
- SQL injection prevention
- Permission filtering
- JWT authentication
- Secret handling
- Rate limiting
- Audit logging
- **Relationships**: References spec requirements FR-018

### 13. Documentation Section

**Location**: After Security  
**Content**:
- Links to all 4 external docs with purpose statements
- **Relationships**: 
  - Links to 4 External Documentation entities
  - Validates file existence

### 14. License Section

**Location**: Footer  
**Content**:
- License type (MIT)
- Link to LICENSE file
- **Relationships**: None

## Feature Summary Entity

**Attributes**:
- Feature Name (string)
- Spec Number (001-013)
- Summary (2-3 sentences)
- Status (Implemented)
- Documentation Link (optional)

**Instances**: 13 total
1. Plugin Foundation
2. LLM Service Layer
3. NL2SQL Pipeline
4. Chat REST API
5. Langfuse Observability
6. Vector Search RAG
7. TDD Gap Analysis
8. Chat Widget
9. Chat Widget Styling
10. Chat Pipeline Integration
11. Realtime Attachment Indexing
12. Conversation History
13. NL2SQL Prompt Optimization

## API Endpoint Entity

**Attributes**:
- Method (GET/POST)
- Path (string)
- Description (string)
- Request Format (JSON schema)
- Response Format (JSON schema)
- Status Codes (list)

**Instances**: 7 total
1. GET /api/assistant/health
2. POST /api/assistant/chat/sessions
3. GET /api/assistant/chat/sessions
4. POST /api/assistant/chat/sessions/<id>/messages
5. GET /api/assistant/chat/sessions/<id>/messages
6. POST /api/assistant/feedback
7. POST /api/assistant/search

## Configuration Setting Entity

**Attributes**:
- Name (string)
- Type (boolean/string/integer/enum)
- Default Value (varies)
- Description (string)
- Category (Global/Widget/Event/Observability/VectorSearch)

**Instances**: ~20 settings across all categories

## CLI Command Entity

**Attributes**:
- Command (string)
- Description (string)
- Arguments (list)
- Example (string)
- Output Format (string)

**Instances**: 5 commands

## External Documentation Entity

**Attributes**:
- Filename (string)
- Path (relative to repo root)
- Purpose Statement (string)
- Link Text (string)

**Instances**: 4 docs
1. DEPLOYMENT.md
2. ACCESSIBILITY.md
3. LANGFUSE_SETUP.md
4. VECTOR_SEARCH_SETUP.md

## Validation Rules

1. **Version Match**: Version badge must match `indico_assistant/version.py`
2. **Setting Accuracy**: All settings must match `default_settings.py`
3. **Endpoint Accuracy**: All endpoints must match `controllers/*.py`
4. **CLI Accuracy**: All commands must match `cli.py`
5. **Dependency Accuracy**: All dependencies must match `pyproject.toml`
6. **Link Validity**: All internal links must resolve to existing anchors
7. **File Links**: All external doc links must point to existing files
8. **TOC Completeness**: TOC must include all major sections

## State Transitions

README has no runtime state - this is documentation only. "States" refer to review status:
- Draft → Under Review → Verified → Published

## Relationships Summary

```
README Document
├── Header Section
├── Table of Contents
│   └── [links to all sections]
├── Features Section
│   └── 13 × Feature Summary
│       └── [optional] → External Documentation
├── Requirements Section
├── Installation Section
├── Configuration Section
│   ├── Global Settings Subsection
│   ├── Chat Widget Settings Subsection
│   │   └── → DEPLOYMENT.md
│   └── Per-Event Settings Subsection
├── API Endpoints Section
│   └── 7 × API Endpoint
├── NL2SQL Pipeline Section
├── CLI Commands Section
│   └── 5 × CLI Command
├── Development Section
│   ├── Setup Subsection
│   ├── Testing Subsection
│   └── Code Quality Subsection
├── Architecture Section
├── Security Section
├── Documentation Section
│   └── 4 × External Documentation
└── License Section
```
