# Implementation Plan: Chat Widget Styling

**Branch**: `009-chat-widget-styling` | **Date**: January 17, 2026 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-chat-widget-styling/spec.md`

## Summary

Fix chat widget transparency by configuring Chainlit's theme.json with fully opaque backgrounds and replace default logos with Indico branding using Chainlit's native logo/avatar system.

## Technical Context

**Language/Version**: Python 3.11+ (Chainlit app), CSS, JSON  
**Primary Dependencies**: Chainlit 2.9.x (copilot widget mode)  
**Storage**: N/A (static configuration files only)  
**Testing**: Manual visual verification, browser dev tools  
**Target Platform**: Modern browsers (Chrome, Firefox, Safari, Edge - latest 2 versions)
**Project Type**: Single project - Chainlit-based chat widget configuration  
**Performance Goals**: Widget loads within 2 seconds  
**Constraints**: Must not break existing widget functionality  
**Scale/Scope**: 3 configuration files + 4 image assets

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Official Indico Plugin Architecture | ✅ N/A | This feature only modifies Chainlit widget config, not Indico plugin code |
| II. API-First Design | ✅ N/A | No API changes; purely frontend configuration |
| III. LLM Provider Abstraction | ✅ N/A | No LLM code changes |
| IV. Graceful Degradation | ✅ Pass | Logo fallbacks handled by Chainlit; CSS failures don't break widget |
| V. Configuration Hierarchy | ✅ N/A | Widget theming is standalone, not event-scoped |
| VI. Test-First Development | ⚠️ Partial | Visual changes verified manually; no automated tests for CSS |

**Gate Status**: ✅ PASS - No constitution violations. Visual-only feature with graceful fallbacks.

## Project Structure

### Documentation (this feature)

```text
specs/009-chat-widget-styling/
├── plan.md              # This file
├── research.md          # Phase 0 output (complete)
├── data-model.md        # Phase 1 output (complete)
├── quickstart.md        # Phase 1 output (complete)
├── contracts/           # Phase 1 output (N/A - no API changes)
│   └── README.md
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (files to modify/create)

```text
chainlit_app/
├── .chainlit/
│   └── config.toml          # MODIFY: Verify UI settings
├── public/
│   ├── theme.json           # MODIFY: Add full CSS variables for opacity
│   ├── widget.css           # MODIFY: Fix opacity values to 1.0
│   ├── logo_light.png       # CREATE: Header logo (light mode)
│   ├── logo_dark.png        # CREATE: Header logo (dark mode)
│   ├── favicon.png          # CREATE/REPLACE: Widget launcher + favicon
│   ├── indico-icon.svg      # EXISTING: May be replaced or removed
│   └── avatars/
│       └── assistant.png    # CREATE: Assistant message avatar
└── app_chnlit.py            # NO CHANGE
```

**Structure Decision**: Minimal changes to existing Chainlit app structure. All modifications are to static assets and JSON/CSS configuration files in the `public/` directory.

## Complexity Tracking

> No complexity violations - this is a simple configuration feature.
