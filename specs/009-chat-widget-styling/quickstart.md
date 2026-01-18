# Quickstart: Chat Widget Styling

**Feature**: 009-chat-widget-styling  
**Created**: January 17, 2026

## Prerequisites

1. Chainlit application running (`chainlit run app_chnlit.py`)
2. Access to Indico logo assets
3. Browser with dev tools for visual verification

## Quick Verification Steps

### 1. Test Current State (Before Changes)

```bash
cd chainlit_app
chainlit run app_chnlit.py
```

Open browser to `http://localhost:8000` and note:
- [ ] Widget background transparency (can you see through it?)
- [ ] Current logo displayed (generic or custom?)
- [ ] Widget launcher button appearance

### 2. Apply Theme Changes

Update `chainlit_app/public/theme.json` with full opacity backgrounds.

Restart Chainlit and verify:
- [ ] Widget background is fully opaque (no page content visible through)
- [ ] Text is clearly readable

### 3. Add Logo Assets

Copy to `chainlit_app/public/`:
- `logo_light.png`
- `logo_dark.png`  
- `favicon.png`

Create `chainlit_app/public/avatars/` and add:
- `assistant.png`

Restart Chainlit and verify:
- [ ] Header shows Indico logo
- [ ] Favicon updated in browser tab
- [ ] Assistant messages show custom avatar

### 4. Fix Widget CSS

Update `chainlit_app/public/widget.css` to use `rgba(255,255,255,1)` or `#ffffff`.

Verify:
- [ ] All widget areas have solid backgrounds
- [ ] No transparency issues remain

## Verification Checklist

| Requirement | How to Verify |
|-------------|---------------|
| SC-001: WCAG AA contrast | Use browser contrast checker extension |
| SC-002: No transparency | Open widget over colorful page content |
| SC-003: All logos display | Visual inspection of header, avatar, launcher |
| SC-004: 2s load time | Browser network tab |
| SC-005: No regressions | Send/receive test messages |

## Common Issues

### Logos not updating
- Clear browser cache (Ctrl+Shift+R / Cmd+Shift+R)
- Check file names match exactly (case-sensitive)

### CSS not applying
- Verify `config.toml` has `custom_css = "/public/widget.css"`
- Check for CSS syntax errors in browser console

### Widget still transparent
- Ensure theme.json uses HSL format: "0 0% 100%" not "#ffffff"
- Check widget.css doesn't override with transparent values
