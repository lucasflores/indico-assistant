# Specification Quality Checklist: Persistent assistant with past chats

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs). The only names used are the existing settings
      and feedback endpoint the requirements must keep (`retention_chat_days`, `/api/assistant/feedback`).
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain (the four open decisions were taken on 2026-09-28; see Context)
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- For the plan: the history sidebar exists only in Chainlit's full-page app, not in the Copilot widget
  (checked in 2.9.5 and 2.12.0). That is why the panel replaces the floating widget.
- For the plan: upgrade Chainlit 2.9.5 → 2.12.0 first (security fixes on websocket session restore in 2.10.1,
  and dependency patches in 2.12.0; Past Chats fixes; `default_sidebar_state = "hidden"`). Remove the legacy
  `[features.mcp.*]` blocks from config.toml. Check the current widget on 2.12.0 before building on it.
- Considered and not chosen (2026-09-28): the Copilot's 2.11 docked "sidebar mode". It docks natively, but
  it has no Past Chats list, and the classic sidebar was asked for.
- The one friction that can't be removed: the panel reloads with every Indico page (under 2 s, usually
  under 1 s). FR-006a keeps it from shifting the page.
