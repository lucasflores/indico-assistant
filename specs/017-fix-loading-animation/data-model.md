# Data Model: Loading Animation Indicator

**Feature**: Loading Animation Indicator  
**Phase**: 1 (Design)  
**Date**: January 28, 2026

## Overview

This feature is a **pure UI enhancement** with no data persistence requirements. There are no database entities, schemas, or storage requirements.

## State Management

While this feature doesn't involve persistent data, it does manage **ephemeral UI state** during the message lifecycle.

### Message Loading State

**Entity**: (Transient, in-memory only)  
**Lifecycle**: Exists only during message processing (typically 1-5 seconds)  
**Scope**: Single user session, single message

#### State Attributes

| Attribute | Type | Description | Lifecycle |
|-----------|------|-------------|-----------|
| `message_object` | `cl.Message` | Chainlit message instance | Created on send, destroyed after update |
| `is_loading` | `boolean` | Implicit state (content is empty) | True from send() until update() |
| `final_content` | `string` | Response text or error message | Set during update() |

#### State Transitions

```
[User sends message]
       ↓
[Create cl.Message(content="")]  ← Loading state begins (is_loading=True)
       ↓
[await msg.send()]  ← Chainlit displays loading indicator
       ↓
[API processing...]  ← Loading indicator remains visible
       ↓
[Response received OR error caught]
       ↓
[msg.content = response_text]
       ↓
[await msg.update()]  ← Loading state ends (is_loading=False)
       ↓
[User sees response]
```

#### State Validation Rules

- Loading state MUST begin before API call
- Loading state MUST end when response arrives OR error occurs
- Message object MUST NOT be abandoned (always updated or explicitly removed)
- Content transitions: empty → response OR empty → error (never empty → empty)

---

## Component Interactions

This feature involves interactions between Chainlit components but no external data systems.

### Component: `@cl.on_message` Handler

**Responsibility**: Orchestrate message lifecycle from loading to response

**Interactions**:
- **Input**: User message (`cl.Message` from user)
- **Creates**: Response message object (`cl.Message(content="")`)
- **Calls**: Indico API (`httpx.AsyncClient.post()`)
- **Updates**: Response message object with final content
- **Output**: Visible response in chat UI

### Component: Chainlit Message Renderer (Framework)

**Responsibility**: Display loading indicator when message content is empty

**Behavior**:
- Detects `content=""` → displays default loading animation
- Receives `msg.update()` → replaces loading animation with content
- Handles theme (light/dark) automatically
- Respects `prefers-reduced-motion` CSS media query

---

## Data Flow

```
User Input
    ↓
[@cl.on_message handler receives user message]
    ↓
[Create empty response message: msg = cl.Message(content="")]
    ↓
[Send to UI: await msg.send()]
    ↓
[Chainlit renders loading indicator in chat]
    ↓
[Handler calls Indico API: response = await client.post(...)]
    ↓
[Handler processes response: reply = data.get("response")]
    ↓
[Update message content: msg.content = reply]
    ↓
[Send update to UI: await msg.update()]
    ↓
[Chainlit replaces loading indicator with response text]
    ↓
User sees response
```

---

## Error State Handling

Loading state must gracefully transition to error state when failures occur.

### Error State Attributes

| Scenario | Loading Transition | Final Content |
|----------|-------------------|---------------|
| API unreachable | Loading → Error | "Unable to reach the assistant service..." |
| Authentication failure | Loading → Error | "Authentication failed. Please sign in again." |
| Authorization failure | Loading → Error | "You do not have permission to access this resource." |
| Validation error | Loading → Error | "Your request could not be validated..." |
| Server error (5xx) | Loading → Error | "The assistant encountered an error..." |
| Timeout | Loading → Error | "Request timed out. Please try again." |

### State Consistency Rules

- Every loading state MUST resolve (success or error)
- Error messages MUST replace loading indicator (not coexist)
- No orphaned loading indicators (all states must terminate)

---

## Concurrency Model

When multiple messages are in loading state simultaneously:

### Independent State Management

Each message maintains its own loading state independently:

```
Message A: [Loading...] → [Response A]
Message B: [Loading...] → [Response B]
Message C: [Loading...] → [Error C]
```

**No shared state** between concurrent messages.

**No global loading flag** needed.

**No queue coordination** required (Chainlit handles ordering).

---

## Memory Characteristics

### Transient State Only

- **No persistent storage**: All state exists in memory during message processing
- **No database writes**: No audit logging of loading events (only responses are logged)
- **No session storage**: Loading state not preserved across page refreshes
- **No caching**: Each message loading state is independent

### Memory Footprint

- **Per message**: ~1KB (Chainlit Message object overhead)
- **Concurrent messages**: Linear growth (N messages = N × 1KB)
- **Cleanup**: Automatic (Python garbage collection after message completes)

---

## Accessibility State

Loading indicators must communicate state to assistive technologies.

### ARIA Attributes (Handled by Chainlit)

Chainlit automatically manages:

- `role="status"` on message container
- `aria-live="polite"` for screen reader announcements
- `aria-busy="true"` during loading (implicit)
- `aria-label` for loading state description

### Screen Reader Announcements

Expected behavior (provided by Chainlit framework):

1. **Loading begins**: "Assistant is typing..." (or similar)
2. **Loading ends**: Message content announced
3. **Error occurs**: Error message announced

**No custom ARIA implementation needed** - Chainlit provides this.

---

## Theme Compatibility

Loading animation must work in both light and dark themes.

### Theme State Integration

Current theme state is managed by Chainlit via CSS custom properties:

```css
:root[data-chainlit-theme="light"] {
  --cl-widget-background: #ffffff;
}

:root[data-chainlit-theme="dark"] {
  --cl-widget-background: #111827;
}
```

### Loading Indicator Theme Behavior

- **Light theme**: Default Chainlit loading animation (dark dots on light background)
- **Dark theme**: Chainlit automatically inverts colors (light dots on dark background)
- **No custom CSS needed**: Chainlit's animation respects theme variables

---

## Performance Characteristics

### Timing Requirements

| Event | Target Latency | Measurement |
|-------|---------------|-------------|
| User sends message → Loading appears | < 100ms | Time from `msg.send()` to DOM update |
| Response received → Content appears | < 50ms | Time from `msg.update()` to DOM update |
| Animation frame rate | 60fps | CSS animation performance |

### Resource Usage

- **CPU**: Minimal (CSS animations, no JavaScript)
- **Memory**: ~1KB per loading message
- **Network**: No additional requests (loading is client-side only)
- **DOM nodes**: +1 per loading message (removed after update)

---

## Summary

**Key Insight**: This feature has **no persistent data model** because loading state is purely ephemeral UI feedback.

**State Management Strategy**: Leverage Chainlit's built-in message lifecycle (`send()` → `update()`) for loading state management.

**Data Flow**: User input → Empty message sent → Loading indicator displayed → API call → Message updated → Response displayed

**Error Handling**: All loading states must terminate in either response content or error message.

**Concurrency**: Each message manages independent loading state with no coordination needed.

**Accessibility**: Chainlit provides ARIA attributes and screen reader support automatically.

**Performance**: Meets <100ms display latency target through native Chainlit APIs.

---

## Phase 1 Completion Checklist

- [x] State lifecycle documented
- [x] Component interactions defined
- [x] Data flow mapped
- [x] Error states specified
- [x] Concurrency model explained
- [x] Accessibility requirements identified
- [x] Theme compatibility addressed
- [x] Performance characteristics defined

**Status**: ✅ Ready for contracts and quickstart generation
