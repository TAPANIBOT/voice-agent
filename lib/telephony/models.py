from dataclasses import dataclass
from enum import Enum
from typing import Optional

class CallStatus(Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    FAILED = "failed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"

@dataclass
class Call:
    id: str
    to: str
    from_: str
    status: CallStatus
    provider: str
    created_at: str
    answered_at: Optional[str] = None
    ended_at: Optional[str] = None
    
@dataclass
class MediaStream:
    codec: str
    sample_rate: int
    channels: int
    encoding: str