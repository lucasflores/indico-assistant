import pytest
from datetime import datetime, timezone
import asyncio
from indico_assistant.event_processing import Event, EventQueue, EventProcessor

class MockEventProcessor(EventProcessor):
    def __init__(self):
        self.processed_events = []
        
    async def process(self, event: Event) -> None:
        self.processed_events.append(event)

@pytest.fixture
def event_queue():
    queue = EventQueue(max_size=10)
    yield queue
    queue.stop()  # Ensure queue is stopped after each test

@pytest.fixture
def mock_processor():
    return MockEventProcessor()

@pytest.fixture
def sample_event():
    return Event(
        event_id="123",
        zoom_id="456",
        password="test",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        timezone="UTC",
        title="Test Event"
    )

async def wait_for_task(task, timeout=1):
    """Helper to wait for a task with timeout"""
    try:
        return await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise

@pytest.mark.asyncio
async def test_event_queue_processing(event_queue, mock_processor, sample_event):
    """Test that events are processed in order"""
    event_queue.register_processor(mock_processor)
    
    # Start processing events
    process_task = asyncio.create_task(event_queue.process_events())
    
    try:
        # Add event to queue
        await event_queue.enqueue(sample_event)
        
        # Wait for event to be processed (with 0.5s timeout)
        start_time = asyncio.get_event_loop().time()
        while len(mock_processor.processed_events) == 0:
            if asyncio.get_event_loop().time() - start_time > 0.5:
                raise TimeoutError("Event not processed within timeout")
            await asyncio.sleep(0.05)
            
        # Verify event was processed
        assert len(mock_processor.processed_events) == 1
        assert mock_processor.processed_events[0].event_id == sample_event.event_id
    finally:
        # Ensure cleanup
        event_queue.stop()
        await wait_for_task(process_task)

@pytest.mark.asyncio
async def test_event_queue_error_handling(event_queue, sample_event):
    """Test that errors in processing don't crash the queue"""
    class ErrorProcessor(EventProcessor):
        async def process(self, event: Event) -> None:
            raise Exception("Test error")
    
    event_queue.register_processor(ErrorProcessor())
    process_task = asyncio.create_task(event_queue.process_events())
    
    try:
        # Add event to queue
        await event_queue.enqueue(sample_event)
        
        # Give it time to process (with timeout)
        await asyncio.sleep(0.1)
        
        # Should not raise exception
        assert event_queue.is_running()
    finally:
        # Ensure cleanup
        event_queue.stop()
        await wait_for_task(process_task)

@pytest.mark.asyncio
async def test_multiple_processors(event_queue, sample_event):
    """Test that multiple processors can handle the same event"""
    processors = [MockEventProcessor() for _ in range(3)]
    for processor in processors:
        event_queue.register_processor(processor)
    
    process_task = asyncio.create_task(event_queue.process_events())
    
    try:
        await event_queue.enqueue(sample_event)
        
        # Wait for all processors to handle the event
        start_time = asyncio.get_event_loop().time()
        while not all(len(p.processed_events) > 0 for p in processors):
            if asyncio.get_event_loop().time() - start_time > 0.5:
                raise TimeoutError("Not all processors handled the event within timeout")
            await asyncio.sleep(0.05)
        
        # Verify all processors handled the event
        for processor in processors:
            assert len(processor.processed_events) == 1
            assert processor.processed_events[0].event_id == sample_event.event_id
    finally:
        event_queue.stop()
        await wait_for_task(process_task)

@pytest.mark.asyncio
async def test_queue_size_limit(event_queue):
    """Test that queue respects its size limit"""
    # Create events up to max size + 1
    events = [
        Event(
            event_id=str(i),
            zoom_id=str(i),
            password="test",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            timezone="UTC",
            title=f"Test Event {i}"
        )
        for i in range(11)  # queue size is 10
    ]
    
    # First 10 events should enqueue immediately
    for i in range(10):
        await event_queue.enqueue(events[i])
    
    # 11th event should timeout
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(event_queue.enqueue(events[10]), timeout=0.1)

@pytest.mark.asyncio
async def test_clean_shutdown(event_queue, mock_processor, sample_event):
    """Test that queue shuts down cleanly and processors finish their work"""
    event_queue.register_processor(mock_processor)
    process_task = asyncio.create_task(event_queue.process_events())
    
    # Enqueue an event and immediately stop
    await event_queue.enqueue(sample_event)
    event_queue.stop()
    
    # Wait for task to complete
    await wait_for_task(process_task)
    
    # Event should still have been processed
    assert len(mock_processor.processed_events) == 1
    assert mock_processor.processed_events[0].event_id == sample_event.event_id
