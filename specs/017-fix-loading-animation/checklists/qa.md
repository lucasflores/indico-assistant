# Manual QA Checklist: Loading Animation Indicator

**Feature**: Loading Animation Indicator  
**Branch**: `017-fix-loading-animation`  
**Date**: January 28, 2026

## Pre-Testing Setup

- [ ] Chainlit app running: `cd chainlit_app && chainlit run app_chnlit.py -w`
- [ ] Indico backend running and accessible
- [ ] Browser DevTools open (for timing and performance checks)
- [ ] Test user authenticated with valid JWT token

---

## User Story 1: Basic Loading Animation (P1)

### Test 1.1: Loading Appears on Message Send

**Steps**:
1. Open chat widget
2. Type a message
3. Click send button
4. Observe immediately (within 100ms)

**Expected**:
- [ ] Loading animation appears in message area
- [ ] Animation shows where response will appear
- [ ] Animation is visible (not hidden or transparent)

**Actual**: _______________

---

### Test 1.2: Loading Replaced by Response

**Steps**:
1. Send a simple message (e.g., "Hello")
2. Wait for response
3. Observe transition from loading to response

**Expected**:
- [ ] Loading animation visible while processing
- [ ] Loading animation disappears when response arrives
- [ ] Response text appears in same location as loading
- [ ] No flicker or jump in UI

**Actual**: _______________

---

### Test 1.3: Loading Persists During Long Processing

**Steps**:
1. Send a complex query that takes 5+ seconds
2. Observe loading animation throughout

**Expected**:
- [ ] Loading animation remains visible entire time
- [ ] No timeout or premature disappearance
- [ ] Animation continues smoothly (no freezing)

**Actual**: _______________

---

### Test 1.4: Mobile Device Compatibility

**Steps**:
1. Open widget on mobile browser (iOS Safari or Android Chrome)
2. Send a message
3. Observe loading behavior

**Expected**:
- [ ] Loading animation displays correctly
- [ ] No layout issues or overflow
- [ ] Animation size appropriate for mobile screen
- [ ] Touch interactions not blocked

**Devices Tested**:
- [ ] iOS Safari (version: _____)
- [ ] Android Chrome (version: _____)

**Actual**: _______________

---

## User Story 2: Multiple Consecutive Messages (P2)

### Test 2.1: Independent Loading States

**Steps**:
1. Send first message
2. Immediately send second message (before first response)
3. Observe both messages

**Expected**:
- [ ] First message shows loading animation
- [ ] Second message shows independent loading animation
- [ ] Both animations visible simultaneously
- [ ] No interference between the two

**Actual**: _______________

---

### Test 2.2: Responses in Correct Order

**Steps**:
1. Send three messages rapidly: "Message 1", "Message 2", "Message 3"
2. Wait for all responses
3. Verify order in chat history

**Expected**:
- [ ] All three show loading independently
- [ ] Responses appear in order: Response 1, Response 2, Response 3
- [ ] No messages lost or duplicated
- [ ] Each loading replaced by correct response

**Actual**: _______________

---

### Test 2.3: No State Leakage Between Messages

**Steps**:
1. Send message A (wait for loading to appear)
2. Send message B (before A completes)
3. Verify A's response updates only A's loading
4. Verify B's response updates only B's loading

**Expected**:
- [ ] Message A loading → Message A response
- [ ] Message B loading → Message B response
- [ ] No cross-contamination

**Actual**: _______________

---

## User Story 3: Error State Handling (P3)

### Test 3.1: Network Error Handling

**Steps**:
1. Stop Indico backend server
2. Send a message
3. Observe loading → error transition

**Expected**:
- [ ] Loading animation appears
- [ ] After timeout, loading replaced with error message
- [ ] Error message: "Unable to reach the assistant service..."
- [ ] No infinite loading spinner

**Actual**: _______________

---

### Test 3.2: Authentication Error

**Steps**:
1. Use expired or invalid JWT token
2. Send a message
3. Observe error handling

**Expected**:
- [ ] Loading animation appears
- [ ] Loading replaced with: "Authentication failed. Please sign in again."
- [ ] No orphaned loading animation

**Actual**: _______________

---

### Test 3.3: Server Error (500)

**Steps**:
1. Trigger 500 error from backend (or mock)
2. Send message
3. Observe error transition

**Expected**:
- [ ] Loading animation appears
- [ ] Loading replaced with server error message
- [ ] Error message clear and actionable

**Actual**: _______________

---

### Test 3.4: Recovery After Error

**Steps**:
1. Trigger any error (network, auth, server)
2. Wait for error message to appear
3. Fix issue (restart server, refresh auth)
4. Send new message

**Expected**:
- [ ] New message shows loading animation normally
- [ ] No lingering error state
- [ ] Loading → response flow works as expected

**Actual**: _______________

---

### Test 3.5: Multiple Consecutive Errors

**Steps**:
1. Trigger error condition
2. Send 3 messages consecutively
3. Observe all three error handling

**Expected**:
- [ ] All three show loading animation
- [ ] All three replace loading with error message
- [ ] No accumulation or stacking of errors
- [ ] Each message handled independently

**Actual**: _______________

---

## Theme Compatibility

### Test 4.1: Light Theme

**Steps**:
1. Ensure widget in light theme (default)
2. Send a message
3. Observe loading animation

**Expected**:
- [ ] Loading animation visible against white background
- [ ] Animation colors provide sufficient contrast
- [ ] Animation doesn't blend into background

**Actual**: _______________

---

### Test 4.2: Dark Theme

**Steps**:
1. Switch to dark theme in Chainlit settings
2. Send a message
3. Observe loading animation

**Expected**:
- [ ] Loading animation visible against dark background
- [ ] Animation colors automatically adjusted
- [ ] Sufficient contrast maintained

**Actual**: _______________

---

## Accessibility

### Test 5.1: Screen Reader Announcement

**Steps**:
1. Enable screen reader (VoiceOver on macOS, NVDA on Windows)
2. Send a message
3. Listen for announcements

**Expected**:
- [ ] Screen reader announces loading state (e.g., "Loading", "Thinking")
- [ ] Screen reader announces response when it arrives
- [ ] Announcements clear and not duplicated

**Screen Reader Used**: _______________

**Actual**: _______________

---

### Test 5.2: Reduced Motion

**Steps**:
1. Enable "Reduce motion" in OS accessibility settings
   - macOS: System Preferences → Accessibility → Display → Reduce motion
   - Windows: Settings → Ease of Access → Display → Show animations
2. Send a message
3. Observe loading indicator

**Expected**:
- [ ] Loading indicator shows (non-animated or minimal animation)
- [ ] Static indicator visible (e.g., static ellipsis "...")
- [ ] No spinning or pulsing animation
- [ ] Functionality preserved

**Actual**: _______________

---

### Test 5.3: Keyboard Navigation

**Steps**:
1. Use only keyboard (no mouse)
2. Navigate to chat input, type message, press Enter
3. Observe loading and response

**Expected**:
- [ ] Loading animation appears without requiring mouse
- [ ] Keyboard focus not lost during loading
- [ ] Can continue typing/navigating while loading
- [ ] No focus traps

**Actual**: _______________

---

## Performance

### Test 6.1: Display Latency

**Steps**:
1. Open browser DevTools → Performance tab
2. Start recording
3. Send a message
4. Stop recording after loading appears
5. Measure time from send to loading visible

**Expected**:
- [ ] Loading appears within 100 milliseconds of message send
- [ ] Measurement: _____ ms

**Actual**: _______________

---

### Test 6.2: Animation Frame Rate

**Steps**:
1. Open DevTools → Performance tab
2. Record while loading animation is active
3. Check frame rate in timeline

**Expected**:
- [ ] Animation maintains 60fps
- [ ] No frame drops or jank
- [ ] Smooth visual animation

**Actual FPS**: _______________

---

### Test 6.3: Scrolling During Loading

**Steps**:
1. Fill chat with many messages
2. Send new message (loading appears)
3. Try scrolling up while loading

**Expected**:
- [ ] Scrolling works normally
- [ ] Loading animation doesn't block scroll
- [ ] No performance degradation while scrolling
- [ ] Loading animation remains visible in viewport

**Actual**: _______________

---

## Edge Cases

### Test 7.1: Page Refresh During Loading

**Steps**:
1. Send message (loading appears)
2. Immediately refresh page (F5 or Cmd+R)
3. Observe behavior after reload

**Expected**:
- [ ] Page reloads without error
- [ ] No orphaned loading state persists
- [ ] Can send new message normally
- [ ] No JavaScript errors in console

**Actual**: _______________

---

### Test 7.2: Widget Close During Loading

**Steps**:
1. Send message (loading appears)
2. Close/minimize widget before response
3. Reopen widget

**Expected**:
- [ ] Widget closes cleanly
- [ ] No errors on reopen
- [ ] Previous message visible (with response if completed)
- [ ] Can send new messages normally

**Actual**: _______________

---

### Test 7.3: Extremely Long Processing (30+ seconds)

**Steps**:
1. Send message that takes >30 seconds to process
2. Observe loading throughout

**Expected**:
- [ ] Loading animation persists entire duration
- [ ] No timeout error before actual completion
- [ ] User can still interact with widget (scroll, etc.)
- [ ] Response eventually arrives and replaces loading

**Actual Duration**: _____ seconds

**Actual**: _______________

---

### Test 7.4: Network Disconnect Mid-Processing

**Steps**:
1. Send message (loading appears)
2. Disconnect network while processing
3. Observe behavior

**Expected**:
- [ ] Loading eventually transitions to error
- [ ] Error message indicates network issue
- [ ] No infinite loading state
- [ ] After reconnect, new messages work

**Actual**: _______________

---

## Browser Compatibility

### Desktop Browsers

- [ ] **Chrome** (version: _____): All tests pass
- [ ] **Firefox** (version: _____): All tests pass
- [ ] **Safari** (version: _____): All tests pass
- [ ] **Edge** (version: _____): All tests pass

### Mobile Browsers

- [ ] **iOS Safari** (version: _____): All tests pass
- [ ] **Android Chrome** (version: _____): All tests pass
- [ ] **Android Firefox** (version: _____): All tests pass

---

## Overall Test Summary

**Date Tested**: _______________  
**Tester**: _______________  
**Environment**: _______________

### Pass/Fail Summary

- User Story 1 (Basic Loading): _____ / _____ tests passed
- User Story 2 (Concurrent Messages): _____ / _____ tests passed
- User Story 3 (Error Handling): _____ / _____ tests passed
- Theme Compatibility: _____ / _____ tests passed
- Accessibility: _____ / _____ tests passed
- Performance: _____ / _____ tests passed
- Edge Cases: _____ / _____ tests passed
- Browser Compatibility: _____ / _____ browsers passed

### Critical Issues Found

1. _____________________________________________
2. _____________________________________________
3. _____________________________________________

### Minor Issues Found

1. _____________________________________________
2. _____________________________________________
3. _____________________________________________

### Sign-off

- [ ] All critical tests pass
- [ ] All accessibility requirements met
- [ ] Performance targets achieved (100ms latency, 60fps)
- [ ] Works on all target browsers
- [ ] No orphaned loading states in any scenario
- [ ] Ready for production deployment

**Tester Signature**: _______________ **Date**: _______________
