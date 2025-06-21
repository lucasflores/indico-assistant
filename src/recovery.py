from typing import TypeVar, Callable, Any, Optional
from functools import wraps
import time
import logging
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar('T')

class RetryableError(Exception):
    """Error that can be retried"""
    pass

class PermanentError(Exception):
    """Error that should not be retried"""
    pass

def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (RetryableError,)
) -> Callable:
    """Decorator for retrying operations with exponential backoff"""
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt + 1 == max_attempts:
                        logger.error(f"Final attempt failed: {e}")
                        raise
                    
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            raise last_exception or RuntimeError("Unexpected retry failure")
        
        return wrapper
    
    return decorator

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: timedelta = timedelta(minutes=5)
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False
    
    def _record_failure(self) -> None:
        """Record a failure and potentially open the circuit"""
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= self.failure_threshold:
            logger.warning("Circuit breaker opened")
            self.is_open = True
    
    def _should_reset(self) -> bool:
        """Check if the circuit should be reset"""
        if not self.last_failure_time:
            return True
        return datetime.now() - self.last_failure_time >= self.reset_timeout
    
    def _reset(self) -> None:
        """Reset the circuit breaker state"""
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if self.is_open:
                if self._should_reset():
                    logger.info("Circuit breaker reset")
                    self._reset()
                else:
                    raise PermanentError("Circuit breaker is open")
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                self._record_failure()
                raise
        
        return wrapper
