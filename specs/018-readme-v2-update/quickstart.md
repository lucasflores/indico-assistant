# Quickstart: README v2.0 Update

**Feature**: 018-readme-v2-update  
**Date**: February 3, 2026

## Prerequisites

- ffmpeg installed (`brew install ffmpeg` on macOS)
- Demo video/GIF file ready

## Implementation Steps

### 1. Optimize Demo GIF (if over 10MB)

```bash
cd /path/to/project

# Check original size
ls -lh docs/demo.gif

# Optimize (640px width, 10 FPS)
ffmpeg -i docs/demo.gif \
  -vf "fps=10,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  -y docs/demo_optimized.gif

# Verify size is under 10MB
ls -lh docs/demo_optimized.gif
```

### 2. Update README Header

```markdown
# Indico Assistant Plugin

**Version**: 2.0.0 | **Last Updated**: February 3, 2026
```

### 3. Add Demo Section (after header, before TOC)

```markdown
## 🎬 Demo

![Indico Assistant Demo](docs/demo_optimized.gif)

*Ask questions about events, search documents, and get instant answers with source citations.*
```

### 4. Update Table of Contents

Add Demo link at the top:
```markdown
- [Demo](#-demo)
```

### 5. Update Core Capabilities Section

Add these new features:
```markdown
- **Personalized Queries**: Ask about your own data with "What meetings do I have?" or "Show my contributions"
- **Source Citations**: Every answer includes inline source links - click to jump directly to the event page or attached document
- **Streaming Responses**: Watch answers appear word-by-word in real-time with visual loading indicators
```

### 6. Update User Interface Section

Add these capabilities:
```markdown
- Loading Animation: Visual indicator while the assistant processes your query
- Token Streaming: Responses appear word-by-word for immediate feedback
```

### 7. Update Supported Questions Table

Add new question types:
```markdown
| **Personal queries** | "What meetings do I have this week?" |
| **Document search** | "What does the budget report say about travel?" |
```

### 8. Update API Response Example

Show new metadata fields:
```json
{
  "metadata": {
    "citations": [...],
    "user_identified": true
  }
}
```

## Verification

1. Push to GitHub and view README
2. Confirm GIF auto-loops
3. Confirm all new features are documented
4. Verify version shows 2.0.0

## Cleanup (Optional)

```bash
# Remove original large GIF to save space
rm docs/demo.gif
```
