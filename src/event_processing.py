from typing import AsyncIterator, Dict, Any, Optional
import asyncio
from datetime import datetime
import aiohttp
from abc import ABC, abstractmethod
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Event(BaseModel):
    event_id: str
    zoom_id: str
    password: str
    start_time: datetime
    end_time: datetime
    timezone: str
    title: Optional[str] = None

class EventProcessor(ABC):
    @abstractmethod
    async def process(self, event: Event) -> None:
        """Process a single event"""
        pass

class EventQueue:
    def __init__(self, max_size: int = 100):
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_size)
        self._stop = False
        self._processors: list[EventProcessor] = []
    
    def register_processor(self, processor: EventProcessor) -> None:
        """Register an event processor"""
        self._processors.append(processor)
    
    async def enqueue(self, event: Event) -> None:
        """Add an event to the queue"""
        await self.queue.put(event)
    
    async def process_events(self) -> None:
        """Process events from the queue"""
        while not self._stop or not self.queue.empty():
            try:
                event = await self.queue.get()
                try:
                    for processor in self._processors:
                        try:
                            await processor.process(event)
                        except Exception as e:
                            logger.error(f"Error processing event {event.event_id}: {e}")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in event processing: {e}")
    
    def stop(self) -> None:
        """Stop processing events"""
        self._stop = True
    
    def is_running(self) -> bool:
        """Check if the queue is running (not stopped)"""
        return not self._stop

class ZoomEventProcessor(EventProcessor):
    async def process(self, event: Event) -> None:
        """Process a Zoom meeting event"""
        logger.info(f"Processing Zoom event {event.event_id}")
        # Implement Zoom-specific processing logic here

class MinutesGenerationProcessor(EventProcessor):
    async def process(self, event: Event) -> None:
        """Generate meeting minutes for an event"""
        logger.info(f"Generating minutes for event {event.event_id}")
        # Implement minutes generation logic here
