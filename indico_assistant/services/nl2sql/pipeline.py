# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Main NL2SQL pipeline orchestrator.

Coordinates the full natural language to SQL translation flow:
classification → generation → validation → execution → error correction → formatting.
"""

import time
from typing import Any, Callable, Optional

from indico_assistant.services.llm import LLMService
from indico_assistant.services.nl2sql.audit import (
    AuditLogger,
    log_cache_hit,
    log_classification,
    log_correction_attempt,
    log_correction_success,
    log_error,
    log_execution,
    log_generation,
    log_validation_rejection,
)
from indico_assistant.services.nl2sql.cache import QueryCache
from indico_assistant.services.nl2sql.classifier import QueryClassifier
from indico_assistant.services.nl2sql.corrector import ErrorCorrector
from indico_assistant.services.nl2sql.executor import QueryExecutor
from indico_assistant.services.nl2sql.formatter import ResultFormatter
from indico_assistant.services.nl2sql.generator import SQLGenerator
from indico_assistant.services.nl2sql.models import (
    PipelineError,
    PipelineErrorType,
    PipelineResult,
)
from indico_assistant.services.nl2sql.permissions import (
    filter_results_by_permission,
    get_user_accessible_event_ids,
)
from indico_assistant.services.nl2sql.schema import SchemaContext
from indico_assistant.services.nl2sql.validator import SQLValidator


class NL2SQLPipeline:
    """
    Main orchestrator for the NL2SQL pipeline.

    This class coordinates all components to convert a natural language
    question into a database query, execute it safely, and return
    formatted results.
    """

    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
        db_session_factory: Callable[[], Any],
        cache: QueryCache | None = None,
        max_rows: int = 1000,
        timeout_seconds: int = 30,
        max_correction_attempts: int = 3,
        allowed_tables: list[str] | None = None,
        audit_enabled: bool = True,
    ) -> None:
        """
        Initialize the NL2SQL pipeline.

        Args:
            llm_service: LLM service for all LLM operations.
            schema_context: Schema context provider.
            db_session_factory: Factory function to get database session.
            cache: Optional query cache. If None, caching is disabled.
            max_rows: Maximum rows to return (default: 1000).
            timeout_seconds: Query timeout in seconds (default: 30).
            max_correction_attempts: Max error correction attempts (default: 3).
            allowed_tables: Optional explicit list of allowed tables.
            audit_enabled: Whether to enable audit logging (default: True).
        """
        self._llm_service = llm_service
        self._schema_context = schema_context
        self._cache = cache
        self._max_correction_attempts = max_correction_attempts
        self._db_session_factory = db_session_factory
        self._audit_enabled = audit_enabled

        # Initialize components
        self._classifier = QueryClassifier(llm_service)
        self._generator = SQLGenerator(llm_service, schema_context)
        self._validator = SQLValidator(schema_context, allowed_tables)
        self._executor = QueryExecutor(
            db_session_factory, max_rows, timeout_seconds
        )
        self._corrector = ErrorCorrector(
            llm_service, schema_context, max_correction_attempts
        )
        self._formatter = ResultFormatter(llm_service)

    def process(
        self,
        question: str,
        user_id: int,
        event_ids: list[int] | None = None,
        user: Any = None,  # Indico User object for permission checks
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> PipelineResult:
        """
        Process a natural language question through the pipeline.

        This is the main entry point for the NL2SQL pipeline. It:
        1. Creates audit log entry (T050)
        2. Checks cache for identical query
        3. Classifies the question
        4. Generates SQL
        5. Validates the SQL
        6. Executes the query
        7. Attempts error correction if needed
        8. Formats the results
        9. Updates audit log on exit (T051)

        Args:
            question: The user's natural language question.
            user_id: The user's ID for permission filtering and audit.
            event_ids: Optional list of event IDs to restrict queries to.
            user: Optional Indico User object for permission verification.
            user_email: Optional user email for audit logging.
            session_id: Optional session ID for grouping queries.
            ip_address: Optional client IP for security audit.

        Returns:
            PipelineResult with the answer or error information.
        """
        start_time = time.time()
        classification_time = 0
        generation_time = 0
        execution_time = 0

        # T050: Create audit log entry at pipeline entry
        audit_logger = AuditLogger(
            self._db_session_factory(), enabled=self._audit_enabled
        )
        audit_log = audit_logger.create_log_entry(
            question=question,
            user_id=user_id,
            user_email=user_email,
            session_id=session_id,
            ip_address=ip_address,
        )

        try:
            # Step 1: Get user's accessible events for permission filtering
            allowed_event_ids = event_ids
            if user is not None:
                allowed_event_ids = get_user_accessible_event_ids(user, event_ids)

            # Step 2: Classify the question
            classify_start = time.time()
            classification_response = self._classifier.classify(question)
            classification_time = int((time.time() - classify_start) * 1000)

            if not classification_response.success or not classification_response.data:
                log_error(
                    audit_log,
                    classification_response.error or "Classification failed",
                )
                return self._error_result(
                    PipelineErrorType.CLASSIFICATION_FAILED,
                    classification_response.error or "Classification failed",
                    "I couldn't understand your question. Please try rephrasing it.",
                    total_time_ms=int((time.time() - start_time) * 1000),
                    classification_time_ms=classification_time,
                )

            classification = classification_response.data
            
            # Log classification result
            log_classification(
                audit_log,
                classification.intent,
                classification.confidence,
            )

            # Check for out-of-scope queries
            if self._classifier.is_out_of_scope(classification):
                log_error(audit_log, f"Out of scope: {classification.intent}")
                return self._error_result(
                    PipelineErrorType.OUT_OF_SCOPE,
                    f"Query classified as out of scope: {classification.intent}",
                    "I can only help with questions about events, registrations, "
                    "and contributions. Please ask about something I can help with.",
                    total_time_ms=int((time.time() - start_time) * 1000),
                    classification_time_ms=classification_time,
                )

            # Step 3: Generate SQL
            gen_start = time.time()
            sql_response = self._generator.generate(
                question, classification, allowed_event_ids
            )
            generation_time = int((time.time() - gen_start) * 1000)

            if not sql_response.success or not sql_response.data:
                log_error(
                    audit_log,
                    sql_response.error or "SQL generation failed",
                )
                return self._error_result(
                    PipelineErrorType.GENERATION_FAILED,
                    sql_response.error or "SQL generation failed",
                    "I had trouble creating a query for your question. "
                    "Please try asking in a different way.",
                    total_time_ms=int((time.time() - start_time) * 1000),
                    classification_time_ms=classification_time,
                    generation_time_ms=generation_time,
                )

            generated_sql = sql_response.data.query
            tables_used = sql_response.data.tables_used
            
            # Log generated SQL
            log_generation(audit_log, generated_sql)

            # Step 4: Validate SQL
            validation_result = self._validator.validate(generated_sql)

            if not validation_result.valid:
                # T052: Log validation rejection with reason
                rejection_reason = "; ".join(validation_result.violations)
                log_validation_rejection(audit_log, rejection_reason)
                return self._error_result(
                    PipelineErrorType.VALIDATION_FAILED,
                    f"Validation failed: {validation_result.violations}",
                    "I generated a query that doesn't meet our safety requirements. "
                    "Please try a simpler question.",
                    total_time_ms=int((time.time() - start_time) * 1000),
                    classification_time_ms=classification_time,
                    generation_time_ms=generation_time,
                    generated_sql=generated_sql,
                    tables_accessed=tables_used,
                )

            # Check cache before execution
            if self._cache is not None:
                cache_key = QueryCache.make_key(user_id, generated_sql, None)
                cached = self._cache.get(cache_key)
                if cached is not None:
                    # Log cache hit
                    log_cache_hit(audit_log)
                    log_execution(audit_log, 0, cached.result.row_count or 0, success=True)
                    # Return cached result with updated timing
                    result = cached.result.model_copy()
                    result.from_cache = True
                    result.total_time_ms = int((time.time() - start_time) * 1000)
                    return result

            # Step 5: Execute query
            exec_start = time.time()
            exec_result = self._executor.execute(generated_sql)
            execution_time = int((time.time() - exec_start) * 1000)

            # Handle execution errors (with potential correction)
            correction_attempts = 0
            corrected = False

            while not exec_result.success and correction_attempts < self._max_correction_attempts:
                correction_attempts += 1
                # T053: Log correction attempt
                log_correction_attempt(audit_log)

                # Attempt error correction
                correction_response = self._corrector.correct(
                    generated_sql, exec_result.error_message or "Unknown error", classification
                )

                if correction_response.success and correction_response.data:
                    # Re-validate corrected SQL
                    corrected_sql = correction_response.data.corrected_query
                    validation_result = self._validator.validate(corrected_sql)

                    if validation_result.valid:
                        # Re-execute with corrected SQL
                        exec_result = self._executor.execute(corrected_sql)
                        if exec_result.success:
                            generated_sql = corrected_sql
                            corrected = True
                            # Log successful correction
                            log_correction_success(audit_log)
                            log_generation(audit_log, corrected_sql)

            if not exec_result.success:
                error_type = PipelineErrorType.EXECUTION_FAILED
                if correction_attempts >= self._max_correction_attempts:
                    error_type = PipelineErrorType.CORRECTION_EXHAUSTED

                log_error(
                    audit_log,
                    exec_result.error_message or "Query execution failed",
                )
                return self._error_result(
                    error_type,
                    exec_result.error_message or "Query execution failed",
                    "I wasn't able to retrieve that information. "
                    "Please try a different question.",
                    total_time_ms=int((time.time() - start_time) * 1000),
                    classification_time_ms=classification_time,
                    generation_time_ms=generation_time,
                    execution_time_ms=execution_time,
                    generated_sql=generated_sql,
                    tables_accessed=tables_used,
                    correction_attempts=correction_attempts,
                )

            # Step 6: Post-execution permission verification (T020b)
            filtered_results = exec_result.rows
            if user is not None:
                filtered_results = filter_results_by_permission(
                    exec_result.rows, user, event_id_key="event_id"
                )

            # Step 7: Format results
            if not filtered_results:
                summary = self._formatter.format_empty_response(question)
            else:
                format_response = self._formatter.format(
                    question, filtered_results, tables_used
                )
                if format_response.success and format_response.data:
                    summary = format_response.data
                else:
                    summary = self._formatter.format_error_response(
                        question, format_response.error or "Formatting failed"
                    )

            total_time = int((time.time() - start_time) * 1000)

            # T051: Log execution success
            log_execution(
                audit_log,
                execution_time_ms=float(execution_time),
                row_count=len(filtered_results),
                success=True,
            )

            result = PipelineResult(
                success=True,
                answer=summary.answer,
                confidence=summary.confidence,
                generated_sql=generated_sql,
                tables_accessed=tables_used,
                row_count=len(filtered_results),
                total_time_ms=total_time,
                classification_time_ms=classification_time,
                generation_time_ms=generation_time,
                execution_time_ms=execution_time,
                correction_attempts=correction_attempts,
                corrected=corrected,
                from_cache=False,
            )

            # Cache the result
            if self._cache is not None:
                cache_key = QueryCache.make_key(user_id, generated_sql, None)
                self._cache.set(cache_key, result)

            return result

        finally:
            # T051: Always commit audit log on exit
            audit_logger.commit()

    def _error_result(
        self,
        error_type: PipelineErrorType,
        message: str,
        user_message: str,
        total_time_ms: int = 0,
        classification_time_ms: int = 0,
        generation_time_ms: int = 0,
        execution_time_ms: int = 0,
        generated_sql: str | None = None,
        tables_accessed: list[str] | None = None,
        correction_attempts: int = 0,
    ) -> PipelineResult:
        """Create an error PipelineResult."""
        return PipelineResult(
            success=False,
            error=PipelineError(
                error_type=error_type,
                message=message,
                user_message=user_message,
            ),
            generated_sql=generated_sql,
            tables_accessed=tables_accessed or [],
            total_time_ms=total_time_ms,
            classification_time_ms=classification_time_ms,
            generation_time_ms=generation_time_ms,
            execution_time_ms=execution_time_ms,
            correction_attempts=correction_attempts,
        )

    @property
    def classifier(self) -> QueryClassifier:
        """Get the query classifier component."""
        return self._classifier

    @property
    def generator(self) -> SQLGenerator:
        """Get the SQL generator component."""
        return self._generator

    @property
    def validator(self) -> SQLValidator:
        """Get the SQL validator component."""
        return self._validator

    @property
    def executor(self) -> QueryExecutor:
        """Get the query executor component."""
        return self._executor

    @property
    def corrector(self) -> ErrorCorrector:
        """Get the error corrector component."""
        return self._corrector

    @property
    def formatter(self) -> ResultFormatter:
        """Get the result formatter component."""
        return self._formatter

    @property
    def cache(self) -> QueryCache | None:
        """Get the query cache if enabled."""
        return self._cache
