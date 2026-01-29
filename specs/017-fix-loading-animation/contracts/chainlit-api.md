# API Contract: Loading Animation Indicator

**Feature**: Loading Animation Indicator  
**Phase**: 1 (Design)  
**Date**: January 28, 2026

## Overview

This feature is a **client-side UI enhancement** with no new API endpoints or external contracts. It modifies the behavior of existing Chainlit message handling but does not change API request/response formats.

## No External API Changes

### Existing API: `/api/assistant/chat` (Indico Plugin)

**Status**: ✅ **UNCHANGED**

The Indico Assistant API endpoint that the Chainlit app calls remains identical:

**Request Contract**:
```json
POST /api/assistant/chat
Headers:
  X-Assistant-Auth: <token>
  Content-Type: application/json

Body:
{
  "message": "string",
  "session_id": "string (optional)",
  "event_id": "integer (optional)"
}
```

**Response Contract**:
```json
200 OK
{
  "response": "string",
  "session_id": "string",
  "metadata": {
    "sql_generated": "string (optional)",
    "confidence": "number (optional)",
    "data_sources": "array (optional)",
    "suggested_followups": "array (optional)"
  }
}
```

**Impact**: Loading animation appears **before** this API call and disappears **after** response is received. The API contract itself is not modified.

---

## Internal Chainlit API Usage

This feature leverages **existing Chainlit framework APIs** - no new contracts are introduced.

### Chainlit Message API

#### `cl.Message` Constructor

**Signature**:
```python
cl.Message(
    content: str = "",
    author: Optional[str] = None,
    # ... other optional parameters
) -> cl.Message
```

**Usage for Loading State**:
```python
msg = cl.Message(content="")  # Empty content triggers loading indicator
```

**Contract**:
- **Input**: `content=""` (empty string)
- **Behavior**: Chainlit displays default loading animation
- **Output**: Message object instance

---

#### `Message.send()` Method

**Signature**:
```python
async def send(self) -> cl.Message
```

**Usage**:
```python
await msg.send()  # Displays message (with loading indicator if content="")
```

**Contract**:
- **Input**: Message object (implicit `self`)
- **Side Effect**: Message appears in chat UI
- **Output**: Same message object (allows chaining)
- **Timing**: Resolves when message is sent to frontend

---

#### `Message.update()` Method

**Signature**:
```python
async def update(self) -> cl.Message
```

**Usage**:
```python
msg.content = "Actual response text"
await msg.update()  # Replaces loading indicator with content
```

**Contract**:
- **Input**: Message object with modified attributes
- **Side Effect**: Message in UI updates (loading → content)
- **Output**: Same message object
- **Timing**: Resolves when update is sent to frontend

---

### Message Lifecycle Contract

**Complete Workflow**:
```python
# Step 1: Create empty message (loading state)
msg = cl.Message(content="")

# Step 2: Send to UI (shows loading)
await msg.send()

# Step 3: Process (API call, business logic)
try:
    response = await api_call()
    msg.content = response
except Exception as e:
    msg.content = f"Error: {e}"

# Step 4: Update UI (replaces loading with content)
await msg.update()
```

**Guarantees**:
- Loading indicator appears immediately upon `send()`
- Loading indicator remains until `update()` is called
- Content replacement is atomic (no flicker)
- Errors can be displayed using the same pattern

---

## Frontend Event Contract

These are **framework-provided events** (Chainlit handles internally):

### Event: Message Sent

**Trigger**: `await msg.send()`

**Frontend Behavior**:
- New message element added to DOM
- If `content=""`, loading animation rendered
- Scroll to bottom of chat
- `aria-live` region updated for screen readers

**Timing**: <100ms from send() call

---

### Event: Message Updated

**Trigger**: `await msg.update()`

**Frontend Behavior**:
- Existing message element updated in DOM
- Loading animation removed
- Content rendered (markdown, links, etc.)
- `aria-live` region announces new content

**Timing**: <50ms from update() call

---

## Error Handling Contract

When API calls fail, the loading state must transition to error state using the same update pattern.

### Error States

| Error Type | HTTP Status | Message Content | Loading Behavior |
|------------|-------------|-----------------|------------------|
| Network Error | N/A (exception) | "Unable to reach the assistant service..." | Loading → Error message |
| Auth Error | 401 | "Authentication failed. Please sign in again." | Loading → Error message |
| Forbidden | 403 | "You do not have permission..." | Loading → Error message |
| Validation Error | 400/422 | "Your request could not be validated..." | Loading → Error message |
| Server Error | 500+ | "The assistant encountered an error..." | Loading → Error message |

**Contract Guarantee**: Every loading state **must** resolve to either response content or error message. No infinite loading states.

---

## Accessibility Contract

Chainlit provides these guarantees (framework-level):

### Screen Reader Contract

**Loading State**:
- **ARIA role**: `status` (implicit)
- **ARIA live**: `polite`
- **Announcement**: "Loading" or "Thinking" (Chainlit default)

**Content Update**:
- **ARIA role**: `article` or `listitem` (Chainlit default)
- **ARIA live**: `polite`
- **Announcement**: Message content read aloud

**Contract**: Screen reader users are notified of both loading state and content updates.

---

### Reduced Motion Contract

**CSS Media Query**:
```css
@media (prefers-reduced-motion: reduce) {
  /* Chainlit disables animation, shows static indicator */
}
```

**Contract**: Users with motion sensitivity preferences see non-animated loading indicator (e.g., static ellipsis instead of pulsing dots).

---

## Theme Contract

Loading animation must adapt to current theme.

### Theme Detection

**Mechanism**: CSS custom properties set by Chainlit

```css
:root[data-chainlit-theme="light"] {
  /* Light theme variables */
}

:root[data-chainlit-theme="dark"] {
  /* Dark theme variables */
}
```

### Loading Animation Theme Behavior

**Contract**:
- **Light theme**: Loading animation uses dark colors (high contrast on white background)
- **Dark theme**: Loading animation uses light colors (high contrast on dark background)
- **Implementation**: Chainlit handles automatically via CSS cascade

**Guarantee**: Loading indicator is always visible regardless of theme.

---

## Performance Contract

### Latency Guarantees

| Operation | Maximum Latency | Measurement Point |
|-----------|----------------|-------------------|
| Loading appears after send | 100ms | `msg.send()` → DOM update |
| Content appears after update | 50ms | `msg.update()` → DOM update |
| Animation frame rate | ≥ 60fps | CSS animation performance |

### Resource Limits

| Resource | Limit | Enforcement |
|----------|-------|-------------|
| Memory per message | 1KB | Python object overhead |
| Concurrent loading states | Unlimited | Each message independent |
| DOM nodes per loading state | 1 | Single message element |

**Contract**: No performance degradation when displaying loading animations.

---

## Concurrency Contract

When multiple messages are loading simultaneously:

### Independent State Guarantee

**Contract**: Each message maintains independent loading state with no shared coordination.

**Example**:
```python
# Message 1
msg1 = cl.Message(content="")
await msg1.send()  # Loading 1 starts

# Message 2 (before Message 1 completes)
msg2 = cl.Message(content="")
await msg2.send()  # Loading 2 starts (independent)

# Later...
msg1.content = "Response 1"
await msg1.update()  # Loading 1 ends, Loading 2 continues

msg2.content = "Response 2"
await msg2.update()  # Loading 2 ends
```

**Guarantee**: Update to one message does not affect loading state of other messages.

---

## Summary

### Contract Type: Internal (Chainlit Framework)

This feature uses **existing Chainlit APIs** with no new contracts:

- ✅ `cl.Message(content="")` - Creates loading state
- ✅ `await msg.send()` - Displays loading indicator
- ✅ `await msg.update()` - Replaces loading with content

### No External API Changes

- ✅ Indico `/api/assistant/chat` endpoint unchanged
- ✅ Request/response formats unchanged
- ✅ Authentication/authorization unchanged

### Framework-Provided Guarantees

- ✅ Accessibility (ARIA, screen readers)
- ✅ Theme adaptation (light/dark)
- ✅ Reduced motion support
- ✅ Performance (<100ms latency)

### Custom Implementation Contracts

- ✅ All loading states must resolve (no infinite loading)
- ✅ Errors replace loading state (not coexist)
- ✅ Independent state per message (no global flags)

---

## Validation Checklist

- [x] No new external APIs introduced
- [x] Existing Chainlit APIs documented
- [x] Message lifecycle contract defined
- [x] Error handling contract specified
- [x] Accessibility contracts identified
- [x] Theme contracts documented
- [x] Performance contracts established
- [x] Concurrency contracts guaranteed

**Status**: ✅ Contract definition complete
