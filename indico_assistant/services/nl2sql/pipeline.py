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

Feature: 005-langfuse-observability (T024-T031)
"""

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Generator, Optional

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

if TYPE_CHECKING:
    from indico_assistant.services.observability.tracer import Tracer
    from indico_assistant.services.embedding.service import EmbeddingService


class NL2SQLPipeline:
    """
    Main orchestrator for the NL2SQL pipeline.

    This class coordinates all components to convert a natural language
    question into a database query, execute it safely, and return
    formatted results.
    
    Feature 005 adds observability via Langfuse integration:
    - Root trace for entire pipeline (T024)
    - Nested spans for each stage (T025-T029)
    - Parent-child span nesting (T030)
    - Error status capture (T031)
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
        max_validation_retries: int = 2,
        allowed_tables: list[str] | None = None,
        audit_enabled: bool = True,
        embedding_service: "EmbeddingService | None" = None,
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
        self._tracer: Optional["Tracer"] = None  # Feature 005

        # Initialize components
        self._classifier = QueryClassifier(llm_service)
        self._generator = SQLGenerator(llm_service, schema_context)
        self._validator = SQLValidator(schema_context, allowed_tables)
        self._executor = QueryExecutor(
            db_session_factory,
            max_rows,
            timeout_seconds,
            embedding_service=embedding_service,
        )
        self._corrector = ErrorCorrector(
            llm_service, schema_context, max_correction_attempts
        )
        self._formatter = ResultFormatter(llm_service)

    def set_tracer(self, tracer: "Tracer") -> None:
        """Set the tracer for observability (Feature 005).
        
        Args:
            tracer: Tracer instance for span instrumentation
        """
        self._tracer = tracer

    @contextmanager
    def _span(self, name: str, **kwargs: Any) -> Generator[Any, None, None]:
        """Create an optional span if tracer is configured (T024).
        
        This helper ensures consistent span handling throughout the pipeline.
        If no tracer is set, yields a no-op context.
        
        Args:
            name: Span name (e.g., 'query_classification')
            **kwargs: Additional span attributes
            
        Yields:
            TracerSpan if tracer is set, otherwise None
        """
        if self._tracer is not None:
            with self._tracer.span(name=name, **kwargs) as span:
                yield span
        else:
            yield None

    def process(
        self,
        question: str,
        user_id: int | None,
        event_ids: list[int] | None = None,
        user: Any = None,  # Indico User object for permission checks
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        conversation_history: list[dict[str, str]] | None = None,
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
                Feature 016 (T010): Now accepts None for unauthenticated users.
            event_ids: Optional list of event IDs to restrict queries to.
            user: Optional Indico User object for permission verification.
            user_email: Optional user email for audit logging.
            session_id: Optional session ID for grouping queries.
            ip_address: Optional client IP for security audit.
            conversation_history: Optional conversation history for context.
                Feature 012: Enable follow-up questions and co-references.
                List of message dicts with 'role' and 'content' keys.

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

            # Step 2: Classify the question (T025)
            classify_start = time.time()
            with self._span("query_classification") as classify_span:
                classification_response = self._classifier.classify(question)
                classification_time = int((time.time() - classify_start) * 1000)
                
                # Update span with result (T030)
                if classify_span is not None:
                    if classification_response.success and classification_response.data:
                        classify_span.update(
                            output=f"intent={classification_response.data.intent}, "
                                   f"confidence={classification_response.data.confidence}",
                            status="success",
                            metadata={"latency_ms": classification_time}
                        )
                    else:
                        classify_span.error(
                            Exception(classification_response.error or "Classification failed"),
                            include_trace=False
                        )

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

            # Step 3: Generate SQL (T026)
            gen_start = time.time()
            with self._span("sql_generation") as gen_span:
                event_id_param = None
                if event_ids and len(event_ids) == 1:
                    event_id_param = event_ids[0]

                sql_response = self._generator.generate(
                    question, 
                    classification, 
                    allowed_event_ids,
                    conversation_history=conversation_history,  # Feature 012: T007
                    user_id=user_id,
                    event_id=event_id_param,
                )
                generation_time = int((time.time() - gen_start) * 1000)
                
                # Update span with result (T030)
                if gen_span is not None:
                    if sql_response.success and sql_response.data:
                        gen_span.update(
                            output=f"tables={sql_response.data.tables_used}",
                            status="success",
                            metadata={
                                "latency_ms": generation_time,
                                "tables_used": sql_response.data.tables_used,
                            }
                        )
                    else:
                        gen_span.error(
                            Exception(sql_response.error or "SQL generation failed"),
                            include_trace=False
                        )

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

            # Step 4: Validate SQL with retry mechanism
            validation_result = self._validator.validate(generated_sql)
            validation_attempts = 0

            # Retry if validation fails, providing violations as feedback
            while not validation_result.valid and validation_attempts < self._max_validation_retries:
                validation_attempts += 1
                rejection_reason = "; ".join(validation_result.violations)
                log_validation_rejection(audit_log, f"Attempt {validation_attempts}: {rejection_reason}")

                # Regenerate SQL with validation feedback
                gen_start = time.time()
                with self._span(f"sql_regeneration_{validation_attempts}") as regen_span:
                    feedback = (
                        f"The generated SQL has validation errors:\n"
                        f"{chr(10).join('- ' + v for v in validation_result.violations)}\n\n"
                        f"Please regenerate the SQL query addressing these issues. "
                        f"Remember: Use JOINs instead of subqueries, no CTEs, no window functions."
                    )
                    
                    sql_response = self._generator.generate(
                        question,
                        classification,
                        allowed_event_ids,
                        conversation_history=conversation_history,
                        user_id=user_id,
                        event_id=event_id_param,
                        validation_feedback=feedback,
                    )
                    generation_time += int((time.time() - gen_start) * 1000)
                    
                    if regen_span is not None:
                        if sql_response.success and sql_response.data:
                            regen_span.update(
                                output="regenerated",
                                status="success",
                                metadata={"attempt": validation_attempts}
                            )
                        else:
                            regen_span.error(
                                Exception(sql_response.error or "Regeneration failed"),
                                include_trace=False
                            )

                if not sql_response.success or not sql_response.data:
                    break  # Give up if regeneration fails

                generated_sql = sql_response.data.query
                tables_used = sql_response.data.tables_used
                log_generation(audit_log, f"Regenerated (attempt {validation_attempts}): {generated_sql}")
                
                # Re-validate the regenerated SQL
                validation_result = self._validator.validate(generated_sql)

            # If still invalid after retries, return error
            if not validation_result.valid:
                rejection_reason = "; ".join(validation_result.violations)
                log_validation_rejection(audit_log, f"Final rejection: {rejection_reason}")
                return self._error_result(
                    PipelineErrorType.VALIDATION_FAILED,
                    f"Validation failed after {validation_attempts} retries: {validation_result.violations}",
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

            # Step 5: Execute query (T027)
            exec_start = time.time()
            with self._span("sql_execution") as exec_span:
                exec_params: dict[str, Any] | None = None
                
                # Inject :user_id parameter if referenced in SQL
                if ":user_id" in generated_sql:
                    exec_params = {"user_id": user_id}
                
                # Inject :event_id parameter if referenced in SQL
                if ":event_id" in generated_sql:
                    if exec_params is None:
                        exec_params = {}
                    if event_ids and len(event_ids) == 1:
                        exec_params["event_id"] = event_ids[0]
                    else:
                        # SQL references :event_id but no event context available
                        # Set to None to avoid SQL execution error
                        exec_params["event_id"] = None

                exec_result = self._executor.execute(
                    generated_sql, params=exec_params, question=question
                )
                execution_time = int((time.time() - exec_start) * 1000)
                
                # Update span with result (T030)
                if exec_span is not None:
                    if exec_result.success:
                        exec_span.update(
                            output=f"rows={len(exec_result.rows) if exec_result.rows else 0}",
                            status="success",
                            metadata={
                                "latency_ms": execution_time,
                                "row_count": len(exec_result.rows) if exec_result.rows else 0,
                            }
                        )
                    else:
                        exec_span.error(
                            Exception(exec_result.error_message or "Execution failed"),
                            include_trace=False
                        )

            # Handle execution errors (with potential correction) (T028)
            correction_attempts = 0
            corrected = False

            while not exec_result.success and correction_attempts < self._max_correction_attempts:
                correction_attempts += 1
                # T053: Log correction attempt
                log_correction_attempt(audit_log)

                # Attempt error correction (T028)
                with self._span(f"sql_correction_{correction_attempts}") as corr_span:
                    correction_response = self._corrector.correct(
                        generated_sql, exec_result.error_message or "Unknown error", classification
                    )
                    
                    # Update span with correction result (T030, T031)
                    if corr_span is not None:
                        if correction_response.success and correction_response.data:
                            corr_span.update(
                                output="correction_generated",
                                status="success",
                                metadata={"attempt": correction_attempts}
                            )
                        else:
                            corr_span.error(
                                Exception(correction_response.error or "Correction failed"),
                                include_trace=False
                            )

                if correction_response.success and correction_response.data:
                    # Re-validate corrected SQL
                    corrected_sql = correction_response.data.corrected_query
                    validation_result = self._validator.validate(corrected_sql)

                    if validation_result.valid:
                        # Re-execute with corrected SQL
                        exec_params = None
                        if ":user_id" in corrected_sql:
                            exec_params = {"user_id": user_id}
                        if ":event_id" in corrected_sql:
                            if exec_params is None:
                                exec_params = {}
                            if event_ids and len(event_ids) == 1:
                                exec_params["event_id"] = event_ids[0]

                        exec_result = self._executor.execute(
                            corrected_sql, params=exec_params, question=question
                        )
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

            # Feature 015: Extract event IDs for citations BEFORE formatting (T015)
            source_event_ids = self._extract_event_ids_from_results(
                filtered_results, event_ids
            )
            
            # Feature 015: Generate citation links if event sources exist
            citations: list[str] | None = None
            if source_event_ids:
                # Import here to avoid circular dependency
                from indico_assistant.services.chat.citations import CitationBuilder
                
                # Get base URL from Indico config first, then fallback to plugin settings
                base_url = 'http://localhost:8000'
                try:
                    from indico.core.config import config
                    if hasattr(config, 'BASE_URL') and config.BASE_URL:
                        base_url = config.BASE_URL.rstrip('/')
                except (ImportError, AttributeError):
                    try:
                        from indico_assistant.plugin import AssistantPlugin
                        plugin = AssistantPlugin.instance
                        if plugin:
                            base_url = plugin.settings.get('base_url', base_url)
                    except (ImportError, AttributeError, RuntimeError):
                        pass
                
                builder = CitationBuilder(base_url=base_url)
                citations = [builder.build_event_citation(eid) for eid in source_event_ids]

            # Step 7: Format results (T029 - response_summarization span)
            with self._span("response_summarization") as format_span:
                if not filtered_results:
                    summary = self._formatter.format_empty_response(question)
                else:
                    format_response = self._formatter.format(
                        question, 
                        filtered_results, 
                        tables_used, 
                        citations=citations,  # Feature 015: T015
                        user_id=user_id,
                        event_id=event_ids[0] if event_ids and len(event_ids) == 1 else None,
                    )
                    if format_response.success and format_response.data:
                        summary = format_response.data
                    else:
                        summary = self._formatter.format_error_response(
                            question, format_response.error or "Formatting failed"
                        )
                
                # Update span with formatting result (T030)
                if format_span is not None:
                    format_span.update(
                        output=f"confidence={summary.confidence}",
                        status="success",
                        metadata={"row_count": len(filtered_results)}
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
                suggested_followups=summary.suggested_followups,
                generated_sql=generated_sql,
                tables_accessed=tables_used,
                row_count=len(filtered_results),
                source_event_ids=source_event_ids,  # Feature 015: citations (already extracted above)
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

    def _extract_event_ids_from_results(
        self,
        results: list[dict[str, Any]],
        context_event_ids: list[int] | None
    ) -> list[int]:
        """Extract event IDs from query results for citation purposes.
        
        Feature: 015-chat-source-citations
        Task: T005
        
        Args:
            results: Query result rows
            context_event_ids: Event IDs from query context (if provided)
            
        Returns:
            List of unique event IDs that contributed to the results
        """
        event_ids = set()
        
        # Strategy 1: Use context event IDs if explicitly provided
        if context_event_ids:
            event_ids.update(context_event_ids)
        
        # Strategy 2: Extract from result rows (look for event_id column)
        for row in results:
            if "event_id" in row and row["event_id"] is not None:
                event_ids.add(int(row["event_id"]))
            # Also check for id column if querying events table directly
            elif "id" in row and isinstance(row.get("id"), int):
                # This might be an event ID if table is events
                event_ids.add(row["id"])
        
        return sorted(list(event_ids))

    def _error_result(
        self,
        error_type: PipelineErrorType,
        message: object,
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
        message_text = self._stringify_error_message(message)
        return PipelineResult(
            success=False,
            error=PipelineError(
                error_type=error_type,
                message=message_text,
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

    @staticmethod
    def _stringify_error_message(message: object) -> str:
        if message is None:
            return "Unknown error"
        if isinstance(message, str):
            return message
        if hasattr(message, "model_dump"):
            try:
                import json

                return json.dumps(message.model_dump(), default=str)
            except Exception:
                return str(message)
        if hasattr(message, "dict"):
            try:
                import json

                return json.dumps(message.dict(), default=str)
            except Exception:
                return str(message)
        return str(message)

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
