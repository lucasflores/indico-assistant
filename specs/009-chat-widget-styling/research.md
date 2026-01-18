# Research: Chat Widget Styling

**Feature**: 009-chat-widget-styling  
**Created**: January 17, 2026  
**Status**: Complete

## Summary

This research resolves technical context for implementing opacity fixes and custom logos in the Chainlit-based chat widget.

---

## 1. Widget Framework: Chainlit Copilot

### Decision
The chat widget uses **Chainlit** as its framework, specifically the "copilot" embedded widget mode.

### Rationale
- Analysis of `chainlit_app/` directory confirms Chainlit usage
- `.chainlit/config.toml` contains Chainlit-specific configuration
- `app_chnlit.py` uses `chainlit` module directly
- Widget is embedded via Chainlit's copilot script

### Relevant Files
- `chainlit_app/.chainlit/config.toml` - Main configuration
- `chainlit_app/public/theme.json` - Theme customization (CSS variables)
- `chainlit_app/public/widget.css` - Custom CSS overrides

---

## 2. Opacity/Background Issue Root Cause

### Decision
The transparency issue stems from **improper CSS selectors and non-matching theme variable configuration**.

### Rationale
Current `widget.css` uses:
```css
background: rgba(255, 255, 255, 0.9);  /* 90% opacity, not 100% */
```

Additionally, the CSS selectors use generic patterns like `[class*="cl-widget"]` which may not match Chainlit's actual DOM structure in the copilot mode.

The proper approach is to:
1. Use **theme.json** CSS variables for backgrounds (Chainlit's native theming)
2. Ensure `--background`, `--card`, `--popover` use fully opaque colors
3. If CSS overrides needed, use fully opaque values: `rgba(255, 255, 255, 1)` or `#ffffff`

### Alternatives Considered
- **Using `!important` overrides**: Rejected - brittle and may break with Chainlit updates
- **Inline styles via JavaScript**: Rejected - unnecessary complexity

---

## 3. Logo Configuration Approach

### Decision
Use **Chainlit's native logo/avatar system** rather than CSS background-image hacks.

### Rationale
Chainlit documentation specifies:

1. **Header Logo**: Place `logo_light.png` and `logo_dark.png` in `/public` folder
2. **Favicon**: Place `favicon.png` in `/public` folder
3. **Assistant Avatar**: Place image in `/public/avatars/` named after the message author (e.g., `assistant.png`)
4. **Widget Button**: Configure via `mountChainlitWidget({ button: { imageUrl: "..." } })` or use favicon

The current code attempts CSS `background-image` for the widget button, which is fragile and may not work correctly.

### Alternatives Considered
- **CSS background-image for all logos**: Rejected - doesn't work reliably with Chainlit's avatar system
- **External URL logos**: Considered but local assets preferred for performance and reliability

---

## 4. Logo Asset Source

### Decision
Copy logo assets from `/Users/lucasflores/dev2/indico/lucas_plugin_dev/indico_assistant/public/` which contains:
- `logo_light.png` (547x224 PNG)
- `logo_dark.svg` (SVG format)
- `favicon.png` (48x48 icon)

### Rationale
These are existing Indico-branded assets already prepared for a similar Chainlit deployment, ensuring brand consistency.

### Notes
- May need to create `logo_dark.png` from the SVG for format consistency
- Avatar image will need to be created/extracted at appropriate size (typically 32x32 or 64x64)

---

## 5. Theme Configuration Structure

### Decision
Update `theme.json` to use Chainlit's CSS variable system with fully opaque backgrounds.

### Key Variables for Opacity
```json
{
  "variables": {
    "light": {
      "--background": "0 0% 100%",    // HSL for white
      "--card": "0 0% 100%",           // Card backgrounds
      "--popover": "0 0% 100%"         // Popup backgrounds
    }
  }
}
```

### Rationale
Chainlit's theme system is based on Shadcn/Radix CSS variables. Using the native system ensures:
- Consistent theming across all widget components
- Automatic dark/light mode support
- No CSS specificity battles

---

## 6. Existing Code Issues Identified

### widget.css Problems
1. Uses 0.9 alpha instead of 1.0 for backgrounds
2. Selectors may not match copilot mode DOM structure
3. Widget button image URL path may be incorrect (`/public/` prefix handling)

### theme.json Status
- Currently has proper structure but uses simplified format
- Primary colors defined (#1f77d0 Indico blue) - good
- Background is white - good, but need to verify all components use it

### config.toml Status
- `custom_css = "/public/widget.css"` is set
- `name = "Assistant"` - may want to change to "Indico Assistant"
- Logo URLs are empty - need to be configured

---

## Implementation Requirements Summary

| Requirement | Implementation Approach |
|-------------|------------------------|
| FR-001: Full opacity | Set `--background`, `--card`, `--popover` to opaque HSL values in theme.json |
| FR-002: Contrast | Use light theme defaults (white bg, dark text) |
| FR-003: All areas opaque | Verify theme.json covers all components; minimal CSS override if needed |
| FR-004: Light theme | Already set in theme.json `"mode": "light"` |
| FR-005: Header logo | Add `logo_light.png` and `logo_dark.png` to `/public` |
| FR-006: Assistant avatar | Add `assistant.png` to `/public/avatars/` |
| FR-007: Launcher icon | Configure favicon.png or widget button imageUrl |
| FR-008: Logo fallback | Chainlit handles gracefully with text fallback |

---

## Files to Modify

1. **chainlit_app/public/theme.json** - Expand with full CSS variables
2. **chainlit_app/public/widget.css** - Fix or replace opacity rules
3. **chainlit_app/.chainlit/config.toml** - Update UI name, verify settings

## Files to Add

1. **chainlit_app/public/logo_light.png** - Header logo (light mode)
2. **chainlit_app/public/logo_dark.png** - Header logo (dark mode)
3. **chainlit_app/public/favicon.png** - Favicon and widget button icon
4. **chainlit_app/public/avatars/assistant.png** - Assistant message avatar
