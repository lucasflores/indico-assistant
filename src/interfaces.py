from abc import ABC, abstractmethod
from typing import Protocol, List, Dict, Any
from datetime import datetime

class AudioProcessor(Protocol):
    def process_audio(self, audio_path: str) -> str:
        """Process audio file and return transcript"""
        ...

class MeetingMinutesGenerator(Protocol):
    def generate_minutes(self, transcript: str) -> str:
        """Generate meeting minutes from transcript"""
        ...

class ZoomBotInterface(ABC):
    @abstractmethod
    def join_meeting(self, meeting_id: str, password: str) -> None:
        """Join a Zoom meeting"""
        pass
    
    @abstractmethod
    def leave_meeting(self) -> None:
        """Leave the current meeting"""
        pass
    
    @abstractmethod
    def start_recording(self) -> None:
        """Start recording the meeting"""
        pass
    
    @abstractmethod
    def stop_recording(self) -> None:
        """Stop recording the meeting"""
        pass

class EventOrchestratorInterface(ABC):
    @abstractmethod
    def fetch_upcoming_events(self) -> List[Dict[str, Any]]:
        """Fetch upcoming events with Zoom meetings"""
        pass
    
    @abstractmethod
    def schedule_bot(self, event: Dict[str, Any]) -> None:
        """Schedule a bot for an upcoming meeting"""
        pass
    
    @abstractmethod
    def process_meeting_recording(self, event_id: str, recording_path: str) -> None:
        """Process meeting recording and generate minutes"""
        pass
