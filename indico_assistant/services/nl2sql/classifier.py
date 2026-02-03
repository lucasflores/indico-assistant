# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Query classifier component for NL2SQL pipeline.

Classifies natural language questions into query intents and extracts
relevant entities using the LLM service.

Feature: 016-user-id-passthrough (T004)
"""

import re
from datetime import datetime, timedelta

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse, QueryClassification, TimeRange


# Classification prompt template (T039: extended for multi-entity queries)
CLASSIFICATION_PROMPT = """You are a query classifier for the Indico event management system.
Analyze the user's question and classify it into one of these intents:

## INTENTS

- **topic_search**: BROAD search for a topic/keyword/project name across ALL content (events, notes, contributions, documents)
- **event_query**: Questions about events, conferences, meetings (count, list, search, basic info, meeting minutes, notes)
- **registration_query**: Questions about event registrations, participants, check-ins
- **contribution_query**: Questions about talks, presentations, contributions, papers
- **speaker_query**: Questions about speakers, presenters, authors of contributions
- **session_query**: Questions about conference sessions, tracks, time blocks
- **attendee_query**: Questions about who attended events or registrations with personal details
- **schedule_query**: Questions about event schedules, timetables, timing of contributions
- **attachment_query**: Questions about file metadata (filenames, types, storage locations)
- **document_content_query**: Questions about the CONTENT within files (what slides say, paper contents)
- **general_info**: General questions about the system or unclear queries
- **out_of_scope**: Questions not related to events/registrations/contributions/documents

## CLASSIFICATION HINTS

### Intent Selection Rules

**PRIORITY 1 - topic_search** (use when searching for a topic/keyword/project across the system):
- User mentions a specific topic, project name, keyword, or subject they want to find
- Questions that reference a NAMED event, meeting, or session (e.g., "Q1 planning session", "daily standup")
- "What's the status on [X]?", "Find anything about [X]", "What do we know about [X]?"
- "Updates on [project]", "Information about [topic]", "Anything related to [X]"
- "What do I need to know before [named event]?" → search for that event name
- The question is exploratory/broad, not asking for specific event metadata
- **CRITICAL**: If user asks about a named topic/project/event (e.g., "Project Aurora", "Q1 planning session"), use topic_search

**PRIORITY 2 - Specific intents** (use when the question is clearly about a specific type of data):
1. **event_query**: Questions about event details, titles, descriptions, venues, dates
   - "What event is this?", "Tell me about this meeting", "Event details"
2. **speaker_query**: WHO is presenting (names only) **WITHOUT content questions**
3. **session_query**: Questions about tracks, session blocks, session times
4. **attendee_query**: WHO attended or registered with personal details
5. **schedule_query**: WHEN things happen, timetables, timing
6. **contribution_query**: Questions about talk titles/abstracts without speaker focus

### CRITICAL: document_content_query Priority

**Use document_content_query** when the question asks about CONTENT within documents (slides, papers, presentations).

**Key indicators for document_content_query**:
- **Presentation content**: "what did [person] present/discuss/say", "summarize presentation", "what was presented"
- **Topics/discussions**: "what topics were covered", "what was discussed"
- **Analysis**: "main points", "key findings", "conclusions"
- **Content keywords**: "says", "mentions", "according to", "talks about", "discusses"

**Do NOT use document_content_query for**:
- Basic event info: "what event is this?", "event details" → **event_query**
- Speaker names: "who presented?" → **speaker_query**
- Talk titles: "what talks are there?" → **contribution_query**

### attachment_query vs document_content_query

- Use **attachment_query** for FILE METADATA only:
    - "What files are attached?"
    - "List the PDFs"

- Use **document_content_query** for CONTENT ACCESS:
    - "What does the presentation say?"
    - "Topics in slides?"

### Hybrid Queries (metadata + content)

- If the question requests BOTH file metadata and content, classify as **document_content_query** and include file metadata entities when possible.

## TIME REFERENCE DEFAULTS

**CRITICAL**: Only extract time_range if the user EXPLICITLY mentions time/date keywords. 
If NO time reference is mentioned, leave time_range as null.

When the user says:
- "recently", "lately" → last 7 days
- "soon", "upcoming" → next 7 days
- "a while ago", "some time ago" → last 30 days
- "this week" → current week (Monday to Sunday)
- "this month" → current calendar month
- "this year" → year-to-date
- "last year" → previous calendar year
- "last week" → previous week
- "next week" → coming week

**DO NOT assume a default time range if none is mentioned.**

## CLASSIFICATION EXAMPLES

**topic_search** (broad keyword/topic search - HIGHEST PRIORITY for named topics):
- "What's the status on Project Aurora?" → searches ALL text fields for "Project Aurora"
- "Find anything about the budget review"
- "What do we know about the new API design?"
- "What do I need to know before tomorrow's Q1 planning session?" → searches for "Q1 Planning Session"
- "Updates on the migration project"
- "Updates on the migration project"
- "Anything related to machine learning?"
- "I missed 3 standups - what's happening with [topic]?"

**event_query** (basic event info - use ONLY for generic event questions WITHOUT a specific topic):
- "What event is this?"
- "Tell me about this meeting"
- "Event details"
- "What's the event title?"

**document_content_query** (search document content):
- "Can you summarize what Lucas presented on?"
- "What did the speaker discuss?"
- "What topics were covered in the talks?"
- "What does the paper say about X?"
- "Main conclusions from presentations?"

**speaker_query** (names/titles only):
- "Who presented at this event?"
- "List all speakers"
- "How many presenters?"

**contribution_query** (talk titles/abstracts):
- "What talks are at this event?"
- "List all contributions"

**CRITICAL**: "What did X present?" = **document_content_query** (content), NOT speaker_query (metadata)

## EXTRACTION RULES

Extract the following from the question:
1. **Entities**: 
   - **Topic/keyword** (CRITICAL for topic_search): Project names, event names (e.g., "Q1 Planning Session"), subject keywords, concepts to search for
   - Event names, person names, file types, categories
   - For topic_search, extract the main search term(s) as entities (e.g., "Project Aurora" → entity, "Q1 planning session" → entity)
   - **Named meetings/sessions**: If the user mentions a specific meeting by name (e.g., "daily standup", "Q1 planning session", "architecture review"), extract it as a topic entity
2. **Time constraints**: Date ranges, relative time references (ONLY if explicitly mentioned)
3. **Filters**: Any specific criteria (e.g., "only physics events", "speakers from CERN")

**CRITICAL for topic_search**: Always extract the topic/keyword/project name/event name as an entity so it can be used in the search query.

## INPUT

USER QUESTION: {question}

TODAY'S DATE: {today}

## OUTPUT

Respond with the classification in the exact format expected by the Pydantic model."""


class QueryClassifier:
    """Classifies questions and extracts entities using LLM."""

    # Default time reference interpretations (FR-003, Clarification Q3)
    TIME_REFERENCE_DEFAULTS = {
        "recently": 7,  # days back
        "lately": 7,
        "soon": 7,  # days forward
        "upcoming": 7,
        "a while ago": 30,
        "some time ago": 30,
        "this week": 7,
        "last week": 7,
        "next week": 7,
        "this month": 30,
    }

    def __init__(self, llm_service: LLMService) -> None:
        """
        Initialize the classifier.

        Args:
            llm_service: The LLM service for classification.
        """
        self._llm_service = llm_service

    def classify(self, question: str) -> LLMResponse[QueryClassification]:
        """
        Classify a natural language question.

        Args:
            question: The user's question in natural language.

        Returns:
            LLMResponse containing QueryClassification with intent and entities.
        """
        # Build the prompt with today's date for time reference resolution
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = CLASSIFICATION_PROMPT.format(question=question, today=today)

        # Use LLM service to generate classification
        response = self._llm_service.generate(
            prompt=prompt,
            response_model=QueryClassification,
        )

        # Post-process time references if needed
        if response.success and response.data:
            response.data = self._resolve_time_references(response.data, question)

        return response

    def _resolve_time_references(
        self, classification: QueryClassification, question: str
    ) -> QueryClassification:
        """
        Resolve vague time references to concrete date ranges.

        Args:
            classification: The initial classification from LLM
            question: The original question for reference lookup

        Returns:
            Updated classification with resolved time ranges.
        """
        question_lower = question.lower()
        today = datetime.now()

        # Explicit year references
        if "last year" in question_lower:
            start_date = today.replace(year=today.year - 1, month=1, day=1).strftime("%Y-%m-%d")
            end_date = today.replace(year=today.year - 1, month=12, day=31).strftime("%Y-%m-%d")
            if classification.time_range is None:
                classification.time_range = TimeRange(start=start_date, end=end_date)
            return classification

        if "this year" in question_lower:
            start_date = today.replace(month=1, day=1).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
            if classification.time_range is None:
                classification.time_range = TimeRange(start=start_date, end=end_date)
            return classification

        # Check if any time reference keywords are in the question
        for keyword, days in self.TIME_REFERENCE_DEFAULTS.items():
            if keyword in question_lower:
                # Create or update time_range based on the keyword type
                if keyword in ("recently", "lately", "a while ago", "some time ago", "last week"):
                    # Past reference
                    start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
                    end_date = today.strftime("%Y-%m-%d")
                elif keyword in ("soon", "upcoming", "next week"):
                    # Future reference
                    start_date = today.strftime("%Y-%m-%d")
                    end_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")
                elif keyword == "this week":
                    # Current week (Monday to Sunday)
                    start_of_week = today - timedelta(days=today.weekday())
                    end_of_week = start_of_week + timedelta(days=6)
                    start_date = start_of_week.strftime("%Y-%m-%d")
                    end_date = end_of_week.strftime("%Y-%m-%d")
                elif keyword == "this month":
                    # Current month
                    start_date = today.replace(day=1).strftime("%Y-%m-%d")
                    # Last day of month
                    if today.month == 12:
                        end_date = today.replace(year=today.year + 1, month=1, day=1)
                    else:
                        end_date = today.replace(month=today.month + 1, day=1)
                    end_date = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    continue

                # Only update if LLM didn't already provide a time_range
                if classification.time_range is None:
                    classification.time_range = TimeRange(
                        start=start_date, end=end_date
                    )
                break  # Use first matching keyword

        return classification

    def is_out_of_scope(self, classification: QueryClassification) -> bool:
        """
        Check if the classification indicates an out-of-scope query.

        Args:
            classification: The classification to check.

        Returns:
            True if the query is out of scope.
        """
        return classification.intent == "out_of_scope"


# Feature 016: Personal query detection (T004)
# Regex patterns for detecting personal queries that require user identity
PERSONAL_PRONOUNS_PATTERN = re.compile(
    r'\b(I|me|my|mine|myself)\b',
    re.IGNORECASE
)

PERSONAL_QUERY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in [
        r'\bmy\s+(meetings?|events?|contributions?|registrations?|talks?|sessions?)\b',
        r'\bam\s+I\s+(registered|attending|speaking|presenting)\b',
        r'\bwhat\s+.*\s+do\s+I\s+have\b',
        r'\bshow\s+me\s+my\b',
        r'\bwhat\s+am\s+I\b',
        r'\bwhere\s+am\s+I\b',
        r'\bwhen\s+do\s+I\b',
        r"\bI'?m\s+(registered|attending|speaking|presenting)\b",
        r'\bfor\s+me\b',
        r'\bmy\s+schedule\b',
        r'\bmy\s+upcoming\b',
    ]
]


def is_personal_query(question: str) -> bool:
    """Check if a question is a personal query requiring user identity.
    
    Personal queries reference the user themselves using pronouns like
    "I", "me", "my" in contexts that require knowing who the user is.
    
    Args:
        question: The user's natural language question
        
    Returns:
        True if the question is a personal query
        
    Feature: 016-user-id-passthrough
    Task: T004
    """
    # Check for personal pronouns first
    if not PERSONAL_PRONOUNS_PATTERN.search(question):
        return False
    
    # Check against specific personal query patterns
    for pattern in PERSONAL_QUERY_PATTERNS:
        if pattern.search(question):
            return True
    
    # If contains personal pronouns and is likely a query context
    # (not just conversational use of "I think" or "I believe")
    conversational_patterns = [
        r'\bI\s+(think|believe|guess|suppose|wonder|hope|wish)\b',
        r"\bI'?d\s+(like|prefer|want)\s+to\s+know\b",
        r'\bcan\s+you\s+tell\s+me\b',
        r'\bI\s+have\s+a\s+question\b',
    ]
    
    for pattern in conversational_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            # These are conversational, not personal data queries
            return False
    
    # If it has personal pronouns and doesn't match conversational patterns,
    # it's likely a personal query
    return bool(PERSONAL_PRONOUNS_PATTERN.search(question))

