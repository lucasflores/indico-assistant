# Research: README v2.0 Update

**Feature**: 018-readme-v2-update  
**Date**: February 3, 2026

## Research Questions

### 1. What video format supports auto-looping on GitHub?

**Decision**: GIF

**Rationale**: GitHub README supports MP4, MOV, and WebM video formats, but none auto-loop. Only GIF format automatically loops when rendered inline. For a demo video that should grab attention without user interaction, GIF is the only viable option.

**Alternatives Considered**:
- **MP4**: Smaller file size, higher quality, but requires click-to-play and doesn't loop
- **WebM**: Not fully supported on GitHub (requires renaming to .mov as workaround)
- **Animated SVG**: Limited to simple animations, not suitable for screen recordings

### 2. What is GitHub's file size limit for inline rendering?

**Decision**: Keep GIF under 10MB

**Rationale**: 
- GitHub allows GIF files up to 10MB to render inline in README
- Files larger than 10MB are still stored but require click-to-view
- Images/GIFs have a hard limit of 10MB (vs 100MB for videos on paid plans)

**Source**: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files

### 3. How to optimize GIF file size while maintaining quality?

**Decision**: Use ffmpeg with palettegen filter

**Rationale**: ffmpeg's two-pass palette generation produces significantly smaller files than naive conversion while maintaining visual quality.

**Command Used**:
```bash
ffmpeg -i demo.gif -vf "fps=10,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -y demo_optimized.gif
```

**Parameters**:
- `fps=10`: Reduced from 15 FPS (adequate for UI demos)
- `scale=640:-1`: Width 640px, height auto (maintains aspect ratio)
- `flags=lanczos`: High-quality scaling algorithm
- `palettegen/paletteuse`: Two-pass palette optimization for smaller size

**Results**:
- Original: 14MB (1920x1078, 15 FPS)
- Optimized: 3.1MB (640x359, 10 FPS)
- Size reduction: 78%

### 4. What features need to be documented?

**Decision**: Document features 015, 016, 017

| Feature | Branch | Description | Documentation Location |
|---------|--------|-------------|------------------------|
| 015 | chat-source-citations | Inline references to events/attachments | Core Capabilities |
| 016 | user-id-passthrough | Personalized queries ("What meetings do I have?") | Core Capabilities + Supported Questions |
| 017 | fix-loading-animation | Loading indicator + token streaming | User Interface |

**Rationale**: These three features were implemented after the last README update (January 20, 2026) and represent significant user-facing functionality.

## Summary

| Question | Answer |
|----------|--------|
| Format for looping | GIF |
| Size limit | 10MB |
| Optimization tool | ffmpeg with palettegen |
| Target specs | 640px, 10 FPS, <10MB |
| Features to document | 015, 016, 017 |
