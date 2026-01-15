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
"""

from datetime import datetime, timedelta

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse, QueryClassification, TimeRange


# Classification prompt template (T039: extended for multi-entity queries)
CLASSIFICATION_PROMPT = """You are a query classifier for an event management system (Indico).
Analyze the user's question and classify it into one of these intents:

INTENTS:
- event_query: Questions about events, conferences, meetings (count, list, search, basic info)
- registration_query: Questions about event registrations, participants, check-ins
- contribution_query: Questions about talks, presentations, contributions, papers
- speaker_query: Questions about speakers, presenters, authors of contributions
- session_query: Questions about conference sessions, tracks, time blocks
- attendee_query: Questions about who attended events or registrations with person details
- schedule_query: Questions about event schedules, timetables, timing of contributions
- attachment_query: Questions about files, materials, documents attached to events
- general_info: General questions about the system or unclear queries
- out_of_scope: Questions not related to events/registrations/contributions

CLASSIFICATION HINTS:
- Use speaker_query if asking about WHO is presenting or authored something
- Use session_query if asking about tracks, session blocks, or session times
- Use attendee_query if asking about WHO attended or registered with personal details
- Use schedule_query if asking about WHEN things happen or timetable entries
- Use contribution_query for questions about talks/papers without speaker focus

Extract any entities (event names, person names, dates, categories) and time constraints.

TIME REFERENCE DEFAULTS (when user says):
- "recently", "lately" → last 7 days
- "soon", "upcoming" → next 7 days  
- "a while ago", "some time ago" → last 30 days
- "this week" → current week (Monday to Sunday)
- "this month" → current calendar month
- "last week" → previous week
- "next week" → coming week

USER QUESTION: {question}

TODAY'S DATE: {today}

Respond with the classification in the exact format expected."""


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
