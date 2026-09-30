# Specification Quality Checklist: Issue reports from the chat

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) in the stories, requirements and success criteria.
      The prototype's findings are kept apart, in "Notes for the plan" at the end.
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain (the open decisions were taken on 2026-09-29; see Context)
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

- Decided by Lucas on 2026-09-29, from the thread C handoff:
  - the conversation is attached, with a box to untick it;
  - a report is kept until 1 year after it closes;
  - no email;
  - reports stay in Indico only.
- Defaults taken without asking. Each can be changed in review:
  - the user can't withdraw or edit a sent report;
  - a copy holds at most 50 messages;
  - a user can send 20 reports a day;
  - the user doesn't see which admin changed the status;
  - the input bar's Report button covers reports that don't point at an answer, so ordinary answers don't carry a
    report button of their own.
