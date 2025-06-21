from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ZoomMeeting:
    event_id: int
    zoom_id: str
    password: str
    start_time: datetime
    end_time: datetime
    timezone: str
    title: Optional[str] = None
    
    def is_active(self) -> bool:
        now = datetime.now(self.start_time.tzinfo)
        return self.start_time <= now <= self.end_time
    
    def time_until_start(self) -> float:
        now = datetime.now(self.start_time.tzinfo)
        return (self.start_time - now).total_seconds()
    
    def time_until_end(self) -> float:
        now = datetime.now(self.end_time.tzinfo)
        return (self.end_time - now).total_seconds()
