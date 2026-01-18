# Data Model: Chat Widget Styling

**Feature**: 009-chat-widget-styling  
**Created**: January 17, 2026  
**Status**: Complete

## Summary

This feature is purely visual/configuration-based and does not require database schema changes. The "data model" consists of configuration files and static assets.

---

## Entities

### 1. Theme Configuration

**File**: `chainlit_app/public/theme.json`

**Purpose**: Controls all CSS variables for the widget appearance.

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | Theme mode: "light" or "dark" |
| `colors` | object | Simplified color shortcuts (legacy) |
| `fonts` | object | Font family definitions |
| `variables.light` | object | CSS variables for light mode |
| `variables.dark` | object | CSS variables for dark mode |

**Key CSS Variables for Opacity**:
- `--background`: Main background color (HSL format)
- `--card`: Card component backgrounds
- `--popover`: Popup/modal backgrounds
- `--foreground`: Text color

### 2. Logo Assets

**Directory**: `chainlit_app/public/`

| Asset | Filename | Format | Purpose |
|-------|----------|--------|---------|
| Header Logo (Light) | `logo_light.png` | PNG | Displayed in widget header on light backgrounds |
| Header Logo (Dark) | `logo_dark.png` | PNG | Displayed in widget header on dark backgrounds |
| Favicon | `favicon.png` | PNG (48x48) | Browser favicon + widget launcher default |

### 3. Avatar Assets

**Directory**: `chainlit_app/public/avatars/`

| Asset | Filename | Format | Purpose |
|-------|----------|--------|---------|
| Assistant Avatar | `assistant.png` | PNG (32x32 or 64x64) | Shown next to assistant messages |

### 4. Custom CSS Overrides

**File**: `chainlit_app/public/widget.css`

**Purpose**: Additional CSS rules that cannot be achieved through theme.json.

**Structure**: CSS selectors targeting Chainlit widget elements.

---

## Relationships

```
theme.json
    ├── controls → widget appearance (colors, fonts, spacing)
    └── affects → all Chainlit components

logo_light.png / logo_dark.png
    └── displayed in → widget header

favicon.png
    ├── displayed in → browser tab
    └── used by → widget launcher button (default)

avatars/assistant.png
    └── displayed next to → assistant messages

widget.css
    └── overrides → specific CSS rules not in theme.json
```

---

## Validation Rules

### Theme Configuration
- HSL values must be in format: "H S% L%" (e.g., "0 0% 100%")
- Mode must be "light" or "dark"
- All opacity-related values must result in fully opaque colors

### Logo Assets
- PNG format required for cross-browser compatibility
- Recommended dimensions:
  - Header logos: Max 300px width, maintain aspect ratio
  - Favicon: 48x48 or 32x32 pixels
  - Avatar: 32x32 or 64x64 pixels

### CSS Overrides
- Must not break widget functionality
- Should use Chainlit's CSS class naming conventions
- Avoid `!important` where possible

---

## State Transitions

N/A - This feature involves static configuration, not runtime state changes.

---

## Notes

- No database migrations required
- No API schema changes required
- All changes are file-based configuration and static assets
