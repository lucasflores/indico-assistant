# Quickstart Guide: Loading Animation Indicator

**Feature**: Loading Animation Indicator  
**Audience**: Developers implementing this feature  
**Estimated Time**: 30 minutes  
**Prerequisites**: Python 3.11+, Chainlit 2.9.5 installed

---

## What You'll Build

Add a visual loading animation to the Chainlit chat widget that appears when users send messages and disappears when responses arrive. This provides immediate feedback that the system is processing their request.

**Before**: User sends message → (no visual feedback) → response appears  
**After**: User sends message → loading animation appears → response replaces loading animation

---

## Quick Setup (5 minutes)

### 1. Verify Environment

```bash
cd /path/to/indico_assistant_plugin/chainlit_app
python --version  # Should be 3.11+
pip show chainlit  # Should be 2.9.5
```

### 2. Understand Current Flow

Open `app_chnlit.py` and locate the `@cl.on_message` handler (around line 225):

```python
@cl.on_message
async def on_message(message: cl.Message):
    """Forward message to Indico assistant API and return response."""
    # ... authentication checks ...
    
    # Currently: API call happens with no loading indicator
    response = await client.post("/api/assistant/chat", ...)
    
    # Currently: Response sent directly
    await cl.Message(content=reply).send()
```

**Problem**: Nothing visible happens between user sending message and response appearing.

---

## Implementation Steps

### Step 1: Create Loading Message (Before API Call)

**Location**: `app_chnlit.py`, inside `@cl.on_message` function  
**Line**: Right after authentication token validation (around line 245)

**Add**:
```python
# Create and send loading message
loading_msg = cl.Message(content="")
await loading_msg.send()
```

**Why**: Empty `content=""` tells Chainlit to display its default loading animation.

---

### Step 2: Capture API Response (No Change to API Logic)

**Location**: Existing API call section (around line 265)  
**Action**: No changes needed to the actual API call

```python
# Existing code - keep as-is
try:
    response = await client.post(
        "/api/assistant/chat",
        json=payload,
        headers={"X-Assistant-Auth": auth_token},
    )
except httpx.RequestError:
    # Error handling continues below...
```

**Why**: API call logic remains unchanged; loading animation runs during this time.

---

### Step 3: Update Loading Message with Response

**Location**: After successful API call and response processing (around line 335)  
**Action**: Replace existing `await cl.Message(content=reply).send()` with update pattern

**Before**:
```python
reply = data.get("response") or "No response returned from assistant."
# ... metadata processing ...
await cl.Message(content=reply).send()
```

**After**:
```python
reply = data.get("response") or "No response returned from assistant."
# ... metadata processing ...

# Update loading message with response
loading_msg.content = reply
await loading_msg.update()
```

**Why**: Updates the existing loading message instead of creating a new message, providing smooth transition.

---

### Step 4: Handle Errors

**Location**: All error handling blocks (lines 270-330)  
**Action**: Update loading message with error content instead of sending new message

**Before** (example from line 300):
```python
if response.status_code == 401:
    await cl.Message(
        content="Authentication failed. Please sign in again."
    ).send()
    return
```

**After**:
```python
if response.status_code == 401:
    loading_msg.content = "Authentication failed. Please sign in again."
    await loading_msg.update()
    return
```

**Repeat for all error conditions**:
- Line ~270: `RequestError` (network errors)
- Line ~285: 401 (authentication)
- Line ~290: 403 (authorization)
- Line ~295: 400/422 (validation)
- Line ~305: 500+ (server errors)
- Line ~320: Other 400+ errors

**Why**: Ensures loading animation always resolves to either response or error, never orphaned.

---

## Testing Your Changes

### Manual Test 1: Basic Loading Animation

```bash
# Start Chainlit app
cd chainlit_app
chainlit run app_chnlit.py -w
```

1. Open browser to Chainlit widget
2. Send a message
3. **Expected**: Loading animation (three pulsing dots) appears immediately
4. **Expected**: Animation is replaced by response after 1-3 seconds

**Pass criteria**: Animation visible before response arrives

---

### Manual Test 2: Multiple Messages

1. Send first message (wait for loading to appear)
2. Immediately send second message (before first response)
3. **Expected**: Both messages show independent loading animations
4. **Expected**: Each loading animation is replaced by its respective response

**Pass criteria**: Each message has its own loading state

---

### Manual Test 3: Error Handling

Simulate error by stopping Indico backend:

1. Stop Indico server (or disconnect network)
2. Send a message
3. **Expected**: Loading animation appears
4. **Expected**: After timeout, error message replaces loading animation
5. **Expected**: No orphaned loading animations remain

**Pass criteria**: Loading transitions to error message

---

### Manual Test 4: Theme Compatibility

1. Test in light theme (default)
2. Switch to dark theme (Chainlit settings)
3. Send messages in both themes
4. **Expected**: Loading animation visible in both themes

**Pass criteria**: Animation contrasts appropriately with background in both themes

---

### Manual Test 5: Accessibility

**Screen Reader Test**:
1. Enable screen reader (VoiceOver on macOS, NVDA on Windows)
2. Send a message
3. **Expected**: Screen reader announces loading state
4. **Expected**: Screen reader announces response when it arrives

**Reduced Motion Test**:
1. Enable reduced motion in OS settings
2. Send a message
3. **Expected**: Loading indicator shown without animation (static)

**Pass criteria**: Accessible to users with assistive technologies

---

## Code Structure After Implementation

```python
@cl.on_message
async def on_message(message: cl.Message):
    """Forward message to Indico assistant API and return response."""
    
    # 1. Validate authentication
    auth_token = _get_auth_token()
    if not auth_token:
        await cl.Message(content="Authentication token missing...").send()
        return
    
    # 2. Create loading message (NEW)
    loading_msg = cl.Message(content="")
    await loading_msg.send()
    
    # 3. Call API
    try:
        response = await client.post("/api/assistant/chat", ...)
    except httpx.RequestError:
        loading_msg.content = "Unable to reach the assistant service..."  # CHANGED
        await loading_msg.update()  # CHANGED
        return
    
    # 4. Handle error responses
    if response.status_code == 401:
        loading_msg.content = "Authentication failed..."  # CHANGED
        await loading_msg.update()  # CHANGED
        return
    # ... other error checks ...
    
    # 5. Process successful response
    data = response.json()
    reply = data.get("response") or "No response..."
    
    # 6. Update loading message with response (CHANGED)
    loading_msg.content = reply
    await loading_msg.update()
```

---

## Common Issues & Solutions

### Issue 1: Loading animation doesn't appear

**Symptom**: Message appears directly without loading animation

**Cause**: `loading_msg.send()` not called before API call

**Fix**: Ensure `await loading_msg.send()` is before `await client.post()`

---

### Issue 2: Two messages appear (loading + response)

**Symptom**: Loading message remains, response appears as separate message

**Cause**: Created new message instead of updating existing one

**Fix**: Use `loading_msg.update()` not `cl.Message(...).send()`

---

### Issue 3: Loading animation never disappears

**Symptom**: Loading animation spins forever

**Cause**: Code path doesn't call `loading_msg.update()`

**Fix**: Ensure ALL code paths (success and errors) update the message

---

### Issue 4: Error appears but loading continues

**Symptom**: Both error message and loading animation visible

**Cause**: Sent new error message instead of updating loading message

**Fix**: Change `await cl.Message(content=error).send()` to:
```python
loading_msg.content = error
await loading_msg.update()
```

---

## Verification Checklist

Before considering implementation complete:

- [ ] Loading animation appears within 100ms of sending message
- [ ] Animation is visible throughout API call duration
- [ ] Response replaces animation (not separate message)
- [ ] All error paths update loading message
- [ ] Multiple concurrent messages show independent loading states
- [ ] Works in both light and dark themes
- [ ] Screen reader announces loading and response
- [ ] Reduced motion setting respected
- [ ] No orphaned loading animations in any scenario

---

## Next Steps

### After Basic Implementation

1. **Write Unit Tests**: Test message lifecycle logic
   ```bash
   pytest tests/unit/test_loading_animation.py
   ```

2. **Add E2E Tests**: Validate visual behavior across browsers
   ```bash
   pytest tests/e2e/test_widget_loading.py
   ```

3. **Document**: Update `chainlit_app/README.md` with loading behavior notes

4. **Performance Check**: Verify animation maintains 60fps
   - Use browser DevTools Performance tab
   - Send messages during recording
   - Check for frame drops

---

## Advanced Customization (Optional)

### Customize Loading Animation CSS

If default Chainlit animation doesn't match Indico branding:

**File**: `chainlit_app/public/widget.css`

**Add**:
```css
/* Custom loading animation for empty messages */
.cl-message-content:empty::after {
  content: "⏳ Processing...";
  color: var(--cl-text-secondary);
  font-style: italic;
}

/* Or use custom spinner */
.cl-message-content:empty::before {
  content: "";
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid var(--cl-primary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Respect reduced motion */
@media (prefers-reduced-motion: reduce) {
  .cl-message-content:empty::before {
    animation: none;
    content: "⋯";  /* Static ellipsis */
  }
}
```

**Note**: Only needed if default Chainlit animation is insufficient. Test thoroughly across themes.

---

## Performance Optimization

### Minimize Latency

**Current**: ~100ms from `send()` to visible loading  
**Target**: <100ms

**Optimization**: Ensure `await loading_msg.send()` is called immediately after auth validation, before any slow operations.

**Bad** (delayed loading):
```python
auth_token = _get_auth_token()
# ... 10 lines of validation logic ...
loading_msg = cl.Message(content="")  # Too late!
```

**Good** (immediate loading):
```python
auth_token = _get_auth_token()
if not auth_token:
    await cl.Message(content="Auth error").send()
    return

loading_msg = cl.Message(content="")  # Immediately after auth check
await loading_msg.send()
# ... then do other validations ...
```

---

## Summary

**What you built**:
- Loading animation appears when user sends message
- Animation persists during API call
- Response replaces animation (smooth transition)
- Errors also replace animation (no orphaned states)
- Works across themes, devices, and accessibility modes

**Files modified**:
- `chainlit_app/app_chnlit.py` (1 file, ~15 line changes)

**Dependencies added**:
- None (uses existing Chainlit 2.9.5 APIs)

**Testing**:
- 5 manual tests (basic, concurrent, errors, themes, accessibility)
- Unit tests for message lifecycle
- E2E tests for visual validation

**Total implementation time**: 30 minutes  
**Total testing time**: 20 minutes  
**Documentation time**: 10 minutes

---

## Getting Help

**Issue with Chainlit APIs?**  
- Chainlit docs: https://docs.chainlit.io/api-reference/message
- Chainlit Discord: https://discord.gg/chainlit

**Issue with Indico integration?**  
- Check `chainlit_app/README.md`
- Review `docs/DEPLOYMENT.md`
- Check Indico plugin logs

**Performance issues?**  
- Use Chrome DevTools Performance tab
- Check network latency to Indico API
- Verify browser supports CSS animations

---

**Ready to implement?** Start with Step 1 and work sequentially through the steps. Test after each step to ensure incremental progress.
