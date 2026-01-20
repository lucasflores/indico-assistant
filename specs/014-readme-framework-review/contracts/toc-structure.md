# Contract: Table of Contents Structure

## Section Requirements

**Location**: After header (title + version badge), before Features section  
**Purpose**: Enable quick navigation to any section  
**Format**: Markdown anchor links with two-level hierarchy

## Content Structure

```markdown
## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Global Settings](#global-settings)
  - [Chat Widget Settings](#chat-widget-settings)
  - [Per-Event Settings](#per-event-settings)
- [Usage](#usage)
  - [NL2SQL Pipeline](#nl2sql-pipeline)
  - [Vector Search](#vector-search)
  - [Chat API](#chat-api)
- [API Endpoints](#api-endpoints)
- [CLI Commands](#cli-commands)
- [Development](#development)
  - [Setup](#setup)
  - [Testing](#testing)
  - [Code Quality](#code-quality)
- [Architecture](#architecture)
- [Security](#security)
- [Documentation](#documentation)
- [License](#license)
- [Contributing](#contributing)
```

## Content Requirements

1. **Top-level sections**:
   - All major sections listed
   - Alphabetically or logically ordered (recommended: logical flow)
   - Markdown link format: `[Text](#anchor)`

2. **Second-level subsections**:
   - Indented with two spaces
   - Only for sections with important subsections (Configuration, Usage, Development)
   - Maximum 2 levels deep (no third-level nesting)

3. **Anchor format**:
   - Lowercase
   - Spaces replaced with hyphens
   - Special characters removed
   - Example: "Global Settings" → `#global-settings`

## Verification Checklist

- [ ] All major sections included
- [ ] Anchor links match actual section headers
- [ ] Two-space indentation for subsections
- [ ] Links clickable in GitHub/IDE markdown preview
- [ ] Logical flow (not alphabetical chaos)
- [ ] No broken links (test in preview)

## Navigation Flow

**Recommended order**:
1. **Discovery**: Features → Requirements
2. **Getting Started**: Installation → Configuration
3. **Usage**: Usage examples → API → CLI
4. **Contributing**: Development → Architecture
5. **Reference**: Security → Documentation → License

## Success Criteria

- User can navigate to any section in <5 seconds
- TOC takes up minimal vertical space (~15-20 lines)
- All links work in GitHub preview
- Logical grouping aids discovery
